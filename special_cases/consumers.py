import json
import re
import asyncio
import traceback
import uuid
from typing import Optional
from datetime import datetime
from django.db import connection
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from asgiref.sync import sync_to_async
from django.conf import settings
from django.db import close_old_connections
from django.db.models import Q, F
from django.utils import timezone
from django.core.cache import cache

from .models import *
from .utils import *

import requests

# -------------------------
# Helpers
# -------------------------
def digits_only(x: str) -> str:
    if not x:
        return ""
    return re.sub(r"\D", "", str(x))

def ws_group_name3(mobile: str) -> str:
    return digits_only(mobile)

# -------------------------
# Database Queries
# -------------------------
@sync_to_async
def get_contacts_page3(page=1, size=30, q="", filter_type="all"):
    """
    Get contacts with pagination and filtering
    filter_type: 'all', 'unread', 'groups'
    """

    qs = ChatContact3.objects.all()

    # Apply filters
    if filter_type == "unread":
        # ✅ FIX: Only show contacts with unread > 0 AND have actual messages
        qs = qs.filter(unread__gt=0)
        # Exclude contacts with "No messages yet" or empty last_msg
        qs = qs.exclude(last_msg__icontains="No messages yet")
        qs = qs.exclude(last_msg="")
        qs = qs.exclude(last_msg__isnull=True)
    elif filter_type == "groups":
        pass

    # Search filter
    if q:
        raw_q = q.strip()
        digits = re.sub(r"\D", "", raw_q)

        filters = Q()
        if digits:
            filters |= Q(mobile__icontains=digits)
        filters |= Q(last_msg__icontains=raw_q)
        qs = qs.filter(filters)

    # Order by last_time DESC (newest first)
    qs = qs.order_by('-last_time')

    # Pagination
    total = qs.count()
    start = (page - 1) * size
    end = start + size
    contacts_qs = qs[start:end]

    contacts = []
    for c in contacts_qs:
        # ✅ FIX: If last_msg is empty, try to get latest message from WhatsApp log
        last_msg = c.last_msg or ""
        if last_msg == "" or last_msg == "No messages yet":
            # Try to get latest message from messages table
            latest_msg = SmsWhatsAppLog3.objects.filter(mobile=c.mobile).order_by('-sent_at').first()
            if latest_msg:
                last_msg = latest_msg.sent_text_message or "[Media]"
                # Update the contact record for next time
                ChatContact3.objects.filter(mobile=c.mobile).update(last_msg=last_msg)
            else:
                # Skip contacts without any messages in unread tab
                if filter_type == "unread":
                    continue
                last_msg = "No messages yet"

        contacts.append({
            "mobile": c.mobile,
            "last_msg": last_msg,
            "last_type": c.last_type or "",
            "last_status": c.last_status or "",
            "unread": c.unread,
            "last_time": c.last_time.isoformat() if c.last_time else None,
        })

    total_pages = (total + size - 1) // size

    # ✅ FIX: Correct unread count for badge
    unread_count = ChatContact3.objects.filter(
        unread__gt=0
    ).exclude(
        last_msg__icontains="No messages yet"
    ).exclude(
        last_msg=""
    ).exclude(
        last_msg__isnull=True
    ).count()

    return {
        "contacts": contacts,
        "total_pages": total_pages,
        "current_page": page,
        "total": total,
        "has_more": page < total_pages,
        "unread_count": unread_count
    }

# messaging/consumers.py - Update get_messages_page_from_db3 function

from datetime import datetime, timedelta
from django.utils import timezone

from django.core.cache import cache
from .utils import format_mobile3
from django.core.files.storage import default_storage

def clear_chat_cache3(mobile):
    formatted = format_mobile3(mobile)

    try:
        cache.delete_pattern(f"chat:{formatted}:*")
        print("🧹 Cache cleared for:", formatted)
    except:
        pass
# ================================
# 🔥 MESSAGE FETCH WITH CACHING
# ================================
@sync_to_async
def get_messages_page_from_db3(mobile, before_date=None, limit=30):
    from .utils import format_mobile3
    from django.db import connection
    from datetime import datetime
    from django.core.cache import cache
    from django.core.files.storage import default_storage

    formatted_mobile = format_mobile3(mobile)
    limit = int(limit or 30)

    cache_key = f"chat:{formatted_mobile}:{before_date or 'latest'}"

    cached = cache.get(cache_key)
    if cached:
        print("⚡ CACHE HIT:", cache_key)
        return cached

    print("🐢 DB HIT:", cache_key)

    with connection.cursor() as cursor:

        # ✅ FIRST LOAD → NO DATE FILTER
        if not before_date:
            query = """
                SELECT id, mobile, sent_text_message, message_type,
                       sent_at, message_id, content_type, media_file,
                       status, customer_name
                FROM special_cases_smswhatsapplog3
                WHERE mobile = %s
                ORDER BY sent_at DESC
                LIMIT %s
            """
            params = [formatted_mobile, limit + 1]

        # ✅ LOAD MORE → USE CURSOR
        else:
            before_date = datetime.fromisoformat(before_date)

            query = """
                SELECT id, mobile, sent_text_message, message_type,
                       sent_at, message_id, content_type, media_file,
                       status, customer_name
                FROM special_cases_smswhatsapplog3
                WHERE mobile = %s AND sent_at < %s
                ORDER BY sent_at DESC
                LIMIT %s
            """
            params = [formatted_mobile, before_date, limit + 1]

        cursor.execute(query, params)
        rows = cursor.fetchall()

    # ✅ pagination logic
    has_more = len(rows) > limit
    rows = rows[:limit]

    # ✅ convert to frontend format (oldest → newest)
    messages = []
    for row in reversed(rows):
        messages.append({
            "id": row[0],
            "mobile": row[1],
            "sent_text_message": row[2] or "",
            "message_type": row[3],
            "sent_at": (
        timezone.localtime(
            timezone.make_aware(row[4], timezone.utc)
        ).isoformat()
        if row[4] else None
    ),
            "message_id": row[5] or "",
            "content_type": row[6] or "text",
            "media_file": default_storage.url(row[7]) if row[7] else "",
            "status": row[8] or "",
            "sender_name": row[9] or "",
        })

    # ✅ cursor (oldest message in this batch)
    next_cursor_date = None
    if has_more and rows:
        next_cursor_date = rows[-1][4].isoformat() if rows[-1][4] else None

    result = {
        "messages": messages,
        "has_more": has_more,
        "next_cursor_date": next_cursor_date
    }

    cache.set(cache_key, result, timeout=30)

    return result
@sync_to_async
def get_initial_messages3(mobile):
    """
    Get initial messages - last 7 days only
    """
    mobile = format_mobile3(mobile)
    seven_days_ago = timezone.now() - timedelta(days=7)

    # Get messages from last 7 days
    qs = SmsWhatsAppLog3.objects.filter(
        mobile=mobile,
        sent_at__gte=seven_days_ago
    ).order_by('sent_at')  # Oldest to newest for display

    messages = list(qs)

    return {
        "messages": [{
            "id": m.id,
            "mobile": m.mobile,
            "sent_text_message": m.sent_text_message or "",
            "message_type": m.message_type,
            "sent_at": m.sent_at.isoformat(),
            "message_id": m.message_id or "",
            "content_type": m.content_type,
            "media_file": m.media_file.url if m.media_file else "",
            "status": m.status or "",
            "sender_name": m.customer_name or "",
        } for m in messages],
        "has_more": SmsWhatsAppLog3.objects.filter(
            mobile=mobile,
            sent_at__lt=seven_days_ago
        ).exists()
    }

@sync_to_async
def create_outgoing_log3(mobile: str, text: str, message_id: str, content_type: str = "text",
                        media_filename: Optional[str] = None, sender_name: str = ""):
    """Create a log for outgoing message"""
    temp_id = message_id or str(uuid.uuid4())
    log = SmsWhatsAppLog3.objects.create(
        customer_name=sender_name,
        mobile=format_mobile3(mobile),
        template_name="manual",
        sent_text_message=text or "",
        status="Pending",
        message_id=temp_id,
        message_type="Sent",
        content_type=content_type,
    )

    ChatContact3.objects.update_or_create(
        mobile=log.mobile,
        defaults={
            "last_msg": text or "",
            "last_time": timezone.now(),
            "last_type": "Sent",
            "last_status": "Pending",
            "unread": 0
        }
    )

    return {
        "id": log.id,
        "mobile": log.mobile,
        "sent_text_message": log.sent_text_message,
        "content_type": log.content_type,
        "media_file": log.media_file.url if log.media_file else "",
        "sent_at": timezone.localtime(log.sent_at).isoformat(),
        "message_type": log.message_type,
        "message_id": log.message_id,
        "status": log.status,
        "sender_name": log.customer_name,
    }

@sync_to_async
def mark_messages_read_db3(mobile: str):
    """Mark all messages as read for a mobile- DON'T update last_time"""
    updated = SmsWhatsAppLog3.objects.filter(
        mobile=format_mobile3(mobile),
        message_type="Received",
        status="Unread"
    ).update(status="Read")

    ChatContact3.objects.filter(mobile=format_mobile3(mobile)).update(unread=0)
    return updated

@sync_to_async
def update_message_status_in_db3(message_id: str, status: str):
    """Update message status in database"""
    return SmsWhatsAppLog3.objects.filter(message_id=message_id).update(status=status)

# -------------------------
# WhatsApp API Helpers
# -------------------------
def send_whatsapp_text_message3(to_number: str, text_body: str) -> dict:
    """Send text message via WhatsApp API"""
    url = f"https://graph.facebook.com/v22.0/{settings.WHATSAPP3_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {settings.WHATSAPP3_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    text_body = text_body[:4096]

    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "text",
        "text": {"body": text_body}
    }

    print(f"Sending text to {to_number}: {text_body[:50]}...")

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        result = resp.json()
        msg_id = result.get('messages', [{}])[0].get('id', '')
        print(f"Text sent successfully. Message ID: {msg_id}")
        return result
    except Exception as e:
        print(f"Send text error: {e}")
        if hasattr(e, 'response') and e.response:
            print(f"Response: {e.response.text}")
        raise


@sync_to_async
def get_unread_count3():
    return ChatContact3.objects.filter(unread__gt=0).count()
# -------------------------
# MAIN CONSUMER
# -------------------------
class ChatConsumer3(AsyncJsonWebsocketConsumer):

    async def connect(self):
        """Handle WebSocket connection"""
        print(f"WebSocket connection attempt at {timezone.now()}")

        self.mobile = None
        self.groups_joined = []
        self.connection_active = True

        try:
            await self.accept()
            print(f"WebSocket accepted - Channel: {self.channel_name}")

            await self._add_to_group("delivery_group3")
            await self._add_to_group("global_contacts3")

            path_mobile = self.scope.get("url_route", {}).get("kwargs", {}).get("mobile")
            if path_mobile:
                gm = ws_group_name3(path_mobile)
                if gm:
                    self.mobile = path_mobile
                    await self._add_to_group(f"chat3_{gm}")
                    print(f"Joined chat group for {path_mobile}")

            await self.send_json({
                "type": "connected",
                "message": "ws_connected",
                "timestamp": timezone.now().isoformat()
            })

            print("Connection successful")

        except Exception as e:
            print(f"ERROR in connect: {e}")
            traceback.print_exc()
            await self.close()

    async def _add_to_group(self, group_name):
        try:
            await self.channel_layer.group_add(group_name, self.channel_name)
            self.groups_joined.append(group_name)
        except Exception as e:
            print(f"Error adding to group {group_name}: {e}")

    async def disconnect(self, close_code):
        print(f"Disconnecting with code: {close_code}")
        self.connection_active = False

        for group_name in self.groups_joined[:]:
            try:
                await self.channel_layer.group_discard(group_name, self.channel_name)
            except Exception as e:
                print(f"Error leaving group {group_name}: {e}")

        self.groups_joined.clear()
        await sync_to_async(close_old_connections)()

    async def receive_json(self, content, **kwargs):
        if not self.connection_active:
            return

        t = content.get("type")
        print(f"Received message type: {t}")

        handlers = {
            "get_contacts": self._handle_get_contacts,
            "search_contacts": self._handle_get_contacts,
            "join": self._handle_join,
            "get_messages": self._handle_get_messages,
            "mark_read": self._handle_mark_read,
            "typing": self._handle_typing,
            "send_message": self._handle_send_message,
        }

        handler = handlers.get(t)
        if handler:
            await handler(content)
        else:
            if self.connection_active:
                await self.send_json({"type": "error", "message": f"unknown type: {t}"})

    async def _handle_get_contacts(self, content):
        try:
            page = int(content.get("page", 1))
            q = content.get("q", "")
            filter_type = content.get("filter", "all")

            res = await get_contacts_page3(page=page, q=q, filter_type=filter_type)

            if self.connection_active:
                await self.send_json({
                    "type": "contacts.page",
                    "contacts": res["contacts"],
                    "page": page,
                    "total_pages": res["total_pages"],
                    "has_more": page < res["total_pages"],
                    "unread_count": res.get("unread_count", 0),
                    "total": res["total"],
                    "filter": filter_type
                })
        except Exception as e:
            print(f"Error in _handle_get_contacts: {e}")
            traceback.print_exc()

    async def _handle_join(self, content):
        try:
            mobile = content.get("mobile")
            if not mobile:
                return

            gm = ws_group_name3(mobile)
            if gm:
                if self.mobile:
                    old_gm = ws_group_name3(self.mobile)
                    if old_gm and f"chat3_{old_gm}" in self.groups_joined:
                        await self.channel_layer.group_discard(f"chat3_{old_gm}", self.channel_name)
                        self.groups_joined.remove(f"chat3_{old_gm}")

                self.mobile = mobile
                await self._add_to_group(f"chat3_{gm}")

                if self.connection_active:
                    await self.send_json({"type": "joined", "mobile": mobile})
        except Exception as e:
            print(f"Error in _handle_join: {e}")

    async def _handle_get_messages(self, content):
        """Handle get messages request - WhatsApp style (load last 7 days first)"""
        try:
            mobile = content.get("mobile")
            before_date = content.get("before_date")  # For date-based pagination
            before_id = content.get("before_id")
            limit = int(content.get("limit", 30))
            print(f"=" * 50)
            print(f"📨 _handle_get_messages called")
            print(f"   Mobile: {mobile}")
            print(f"   Before date: {before_date}")
            print(f"   Before ID: {before_id}")
            print(f"   Limit: {limit}")

            if not mobile:
                print("❌ No mobile provided")
                return
            # Get messages (first load = last 7 days, then older)
            res = await get_messages_page_from_db3(mobile, before_date,limit)
            print(f"📊 Query result:")
            print(f"   Messages count: {len(res['messages'])}")
            print(f"   Has more: {res['has_more']}")
            print(f"   Next cursor: {res.get('next_cursor_date')}")
            if len(res['messages']) > 0:
                print(f"   First message ID: {res['messages'][0].get('id')}")
                print(f"   First message text: {res['messages'][0].get('sent_text_message')[:50]}")
            else:
                print(f"   ⚠️ NO MESSAGES FOUND in query result!")
                formatted_mobile = format_mobile3(mobile)
                direct_count = await sync_to_async(SmsWhatsAppLog3.objects.filter(mobile=formatted_mobile).count)()
                print(f"   🔍 Direct DB check for {formatted_mobile}: {direct_count} messages")


            if self.connection_active:
                await self.send_json({
                    "type": "messages.page",
                    "mobile": mobile,
                    "messages": res["messages"],
                    "has_more": res["has_more"],
                    # "last_id": res["last_id"],
                    "next_cursor_date": res.get("next_cursor_date"),
                    "is_initial": before_date is None and before_id is None  # Flag for first load

                })
        except Exception as e:
            print(f"Error in _handle_get_messages: {e}")
            traceback.print_exc()

    async def _handle_mark_read(self, content):
        try:
            mobile = content.get("mobile")
            if not mobile or not self.connection_active:
                return

            await mark_messages_read_db3(mobile)

            gm = ws_group_name3(mobile)

            if gm:
                await self.channel_layer.group_send(
                    f"chat3_{gm}",
                    {
                        "type": "delivery.update",
                        "message_id": "",
                        "status": "Read",
                        "mobile": mobile
                    }
                )

            await self.channel_layer.group_send(
                "global_contacts3",
                {
                    "type": "contact.update",
                    "contact": {
                        "mobile": mobile,
                        "unread": 0,
                        "last_status": "Read",
                        # "last_time": timezone.now().isoformat()
                    }
                }
            )

            if self.connection_active:
                await self.send_json({
                    "type": "marked_read",
                    "mobile": mobile
                })

        except Exception as e:
            print(f"Error in _handle_mark_read: {e}")

    async def _handle_typing(self, content):
        try:
            mobile = content.get("mobile")
            state = content.get("state", False)
            if mobile and self.connection_active:
                gm = ws_group_name3(mobile)
                if gm:
                    await self.channel_layer.group_send(
                        f"chat3_{gm}",
                        {"type": "typing.event", "mobile": mobile, "state": state}
                    )
        except Exception as e:
            print(f"Error in _handle_typing: {e}")

    async def _handle_send_message(self, content):
        """Handle send message request - FIXED VERSION"""
        try:
            mobile = content.get("mobile")
            text = content.get("text", "")
            content_type = content.get("content_type", "text")

            if not mobile:
                return

            # Get agent name
            agent_name = None
            try:
                sid = self.scope["session"].get("messaging_user")
                if sid:
                    from django.contrib.auth.models import User
                    u = await sync_to_async(User.objects.filter(id=sid).first)()
                    if u:
                        agent_name = u.username
            except:
                pass

            # Create pending message log
            created = await create_outgoing_log3(mobile, text, "", content_type, sender_name=agent_name or "")
            created["sender_name"] = agent_name

            # Clear cache
            cache.clear()

            # Real-time contact update
            await self.channel_layer.group_send(
                "global_contacts3",
                {
                    "type": "contact.update",
                    "contact": {
                        "mobile": mobile,
                        "last_msg": text or "",
                        "last_time": timezone.now().isoformat(),
                        "last_type": "Sent",
                        "last_status": "Pending",
                        "unread": 0
                    }
                }
            )

            # Show message in chat immediately
            gm = ws_group_name3(mobile)
            if gm and self.connection_active:
                await self.channel_layer.group_send(
                    f"chat3_{gm}",
                    {"type": "new_message", "message": created}
                )

            # Send to WhatsApp (background task)
            asyncio.create_task(
                self._send_to_whatsapp_background(
                    mobile, text, content_type, created["id"], agent_name
                )
            )

            # Acknowledge
            if self.connection_active:
                await self.send_json({
                    "type": "sent_ok",
                    "local_id": created["id"]
                })

        except Exception as e:
            print(f"Error in _handle_send_message: {e}")
            traceback.print_exc()

    async def _send_to_whatsapp_background(self, mobile, text, content_type, log_id, agent_name):
        """Send message to WhatsApp in background - FIXED INDENTATION"""
        try:
            msg_id = ""

            # Send via WhatsApp API
            if content_type == "text":
                send_resp = await sync_to_async(send_whatsapp_text_message3)(mobile, text)
                if isinstance(send_resp, dict) and "messages" in send_resp:
                    msg_id = send_resp["messages"][0].get("id", "")
            else:
                print(f"Media message type {content_type} should be sent via API")
                await sync_to_async(
                    lambda: SmsWhatsAppLog3.objects.filter(id=log_id).update(
                        status="Failed",
                        error_message="Media messages must be sent via API endpoint"
                    )
                )()
                return

            print(f"Background send - Message ID from WhatsApp: {msg_id}")

            # Update log with message_id and status
            if msg_id:
                await sync_to_async(
                    lambda: SmsWhatsAppLog3.objects.filter(id=log_id).update(
                        message_id=msg_id,
                        status="Sent"
                    )
                )()

                # Update contact status
                await sync_to_async(
                    lambda: ChatContact3.objects.filter(mobile=mobile).update(
                        last_status="Sent"
                    )
                )()

                gm = ws_group_name3(mobile)
                if gm:
                    print(f"Sending delivery.update to group: chat3_{gm} with status Sent")
                    await self.channel_layer.group_send(
                        f"chat3_{gm}",
                        {
                            "type": "delivery.update",
                            "message_id": msg_id,
                            "status": "Sent",
                            "mobile": mobile
                        }
                    )
                print(f"WhatsApp msg sent: {msg_id}")
            else:
                print("No message_id received from WhatsApp - send failed")
                await sync_to_async(
                    lambda: SmsWhatsAppLog3.objects.filter(id=log_id).update(
                        status="Failed",
                        error_message="No response from WhatsApp"
                    )
                )()

        except Exception as e:
            print(f"WhatsApp send error: {e}")
            traceback.print_exc()
            await sync_to_async(
                lambda: SmsWhatsAppLog3.objects.filter(id=log_id).update(
                    status="Failed",
                    error_message=str(e)
                )
            )()

            if self.connection_active:
                await self.send_json({
                    "type": "send_error",
                    "error": str(e),
                    "local_id": log_id
                })

    # -------------------------
    # Group event handlers
    # -------------------------
    async def new_message(self, event):
        if self.connection_active:
            await self.send_json({
                "type": "new.message",
                "message": event.get("message", {})
            })
            unread_count = await get_unread_count3()
            await self.send_json({
                "type": "unread.update",
                "unread_count": unread_count
        })

    async def delivery_update(self, event):
        if self.connection_active:
            print(f"📬 Delivery update event received: {event}")
            await self.send_json({
                "type": "delivery.update",
                "message_id": event.get("message_id"),
                "status": event.get("status"),
                "mobile": event.get("mobile", ""),
            })

    async def typing_event(self, event):
        if self.connection_active:
            await self.send_json({
                "type": "typing",
                "mobile": event.get("mobile"),
                "state": event.get("state", False)
            })

    async def contact_update(self, event):
        if self.connection_active:
            await self.send_json({
                "type": "contact.update",
                "contact": event.get("contact", {})
            })
            unread_count = await get_unread_count3()
            await self.send_json({
                "type": "unread.update",
                "unread_count": unread_count
        })
    async def unread_update(self, event):
        """Handle unread count updates"""
        if self.connection_active:
            unread_count = event.get("unread_count", 0)
            print(f"📊 Unread update received: {unread_count}")
            await self.send_json({
                "type": "unread.update",
                "unread_count": unread_count
            })
    
    # ⭐ ADD THIS FOR SAFETY ⭐
    async def presence_update(self, event):
        """Handle presence updates"""
        if self.connection_active:
            await self.send_json({
                "type": "presence.update",
                "mobile": event.get("mobile"),
                "status": event.get("status")
            })
