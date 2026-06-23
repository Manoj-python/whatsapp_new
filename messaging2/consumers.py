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

def ws_group_name2(mobile: str) -> str:
    return digits_only(mobile)

# -------------------------
# Database Queries
# -------------------------
from django.db.models import Q, OuterRef, Subquery
from .models import ChatContact2, SmsWhatsAppLog2, Case

@sync_to_async
def get_contacts_page2(page=1, size=30, q="", filter_type="all", level=None, group_ids=None):
    """
    For ESC2, ESC3, ESC4: returns a list of CASES (one per row) so that all cases are visible,
    including duplicates for the same mobile.
    For ESC1 and ESC5: returns a list of CONTACTS (unique mobiles) as before.
    """
    import re  # ensure re is imported

    # ----- ESC2, ESC3, ESC4: show CASES -----
    if level and level not in ['ESC1', 'ESC5']:
        # Start from the Case table
        case_qs = Case.objects.filter(current_level=level)
        if group_ids:
            case_qs = case_qs.filter(group_id__in=group_ids)

        # Search: by case_id, mobile, customer_name
        if q:
            raw_q = q.strip()
            digits = re.sub(r"\D", "", raw_q)
            filters = Q()
            if digits:
                filters |= Q(mobile__icontains=digits)
            filters |= Q(case_id__icontains=raw_q) | Q(customer_name__icontains=raw_q)
            case_qs = case_qs.filter(filters)

        # Order: high priority first, then newest
        case_qs = case_qs.order_by('-priority', '-created_at')

        total = case_qs.count()
        start = (page - 1) * size
        end = start + size
        cases = case_qs[start:end]

        contacts = []
        for case in cases:
            # Get ChatContact2 for this mobile (if exists)
            cc = ChatContact2.objects.filter(mobile=case.mobile).first()
            last_msg = cc.last_msg if cc else "No messages yet"
            unread = cc.unread if cc else 0
            last_time = cc.last_time if cc else case.created_at

            contacts.append({
                "mobile": case.mobile,
                "case_id": case.case_id,                    # new field
                "customer_name": case.customer_name or "",
                "last_msg": last_msg,
                "last_type": "Case",
                "last_status": case.status,
                "unread": unread,
                "last_time": last_time.isoformat() if last_time else None,
                "current_level": case.current_level,
                "group_name": case.group.name if case.group else "",
                "is_case": True,                            # flag for frontend
            })

        total_pages = (total + size - 1) // size if total > 0 else 1
        # Unread count not used for ESC2/3/4 (return 0)
        return {
            "contacts": contacts,
            "total_pages": total_pages,
            "current_page": page,
            "total": total,
            "has_more": page < total_pages,
            "unread_count": 0
        }

    # ----- ESC1 and ESC5: show CONTACTS (unchanged logic) -----
    # Subquery to get the latest case for each mobile
    latest_case = Case.objects.filter(mobile=OuterRef('mobile')).order_by('-created_at')
    # Annotate group_id and group_name
    qs = ChatContact2.objects.annotate(
        latest_group_id=Subquery(latest_case.values('group_id')[:1]),
        latest_group_name=Subquery(latest_case.values('group__name')[:1])
    )

    # Apply level filter (based on current_level on ChatContact2)
    if level and level != 'ESC1':
        qs = qs.filter(current_level=level)

    # Apply unread/assigned filters
    if filter_type == "unread":
        qs = qs.filter(unread__gt=0)
        qs = qs.exclude(last_msg__icontains="No messages yet")
        qs = qs.exclude(last_msg="")
        qs = qs.exclude(last_msg__isnull=True)
    elif filter_type == "assigned":
        if level:
            qs = qs.filter(current_level=level)
        qs = qs.exclude(last_msg__icontains="No messages yet")

    # Search filter (mobile, last_msg, and group name from annotation)
    if q:
        raw_q = q.strip()
        digits = re.sub(r"\D", "", raw_q)
        filters = Q()
        if digits:
            filters |= Q(mobile__icontains=digits)
        filters |= Q(last_msg__icontains=raw_q)
        # Also search in the annotated group name
        filters |= Q(latest_group_name__icontains=raw_q)
        qs = qs.filter(filters)

    # Group filter (if user is non‑agent and non‑admin)
    if group_ids and level and level != 'ESC1' and level != 'ESC5':
        qs = qs.filter(latest_group_id__in=group_ids)

    # Order by last_time DESC (already indexed)
    qs = qs.order_by('-last_time')

    # Paginate in the database
    total = qs.count()
    start = (page - 1) * size
    end = start + size
    contacts_qs = qs[start:end]

    # Build the contact list (only paginated contacts, no extra queries)
    contacts = []
    for c in contacts_qs:
        last_msg = c.last_msg or ""
        if last_msg == "" or last_msg == "No messages yet":
            # Only fetch latest message if needed (optional, but could be optimized further)
            latest_msg = SmsWhatsAppLog2.objects.filter(mobile=c.mobile).order_by('-sent_at').first()
            if latest_msg:
                last_msg = latest_msg.sent_text_message or "[Media]"
                # Async update (optional, but fine)
                ChatContact2.objects.filter(mobile=c.mobile).update(last_msg=last_msg)
            else:
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
            "current_level": c.current_level or "ESC1",
            "group_name": c.latest_group_name,
            # No is_case flag – frontend will treat as contact
        })

    total_pages = (total + size - 1) // size if total > 0 else 1

    # Unread count (only for agents/admins)
    unread_count = 0
    if not level or level in ['ESC1', 'ESC5']:
        unread_count = ChatContact2.objects.filter(
            unread__gt=0
        ).exclude(
            last_msg__icontains="No messages yet"
        ).exclude(
            last_msg=""
        ).count()

    return {
        "contacts": contacts,
        "total_pages": total_pages,
        "current_page": page,
        "total": total,
        "has_more": page < total_pages,
        "unread_count": unread_count
    }

# messaging/consumers.py - Update get_messages_page_from_db2 function

from datetime import datetime, timedelta
from django.utils import timezone

from django.core.cache import cache
from .utils import format_mobile2
from django.core.files.storage import default_storage

def clear_chat_cache2(mobile):
    formatted = format_mobile2(mobile)

    try:
        cache.delete_pattern(f"chat:{formatted}:*")
        print("🧹 Cache cleared for:", formatted)
    except:
        pass
# ================================
# 🔥 MESSAGE FETCH WITH CACHING
# ================================
@sync_to_async
def get_messages_page_from_db2(mobile, before_date=None, limit=30):
    from .utils import format_mobile2
    from django.db import connection
    from datetime import datetime
    from django.core.cache import cache
    from django.core.files.storage import default_storage

    formatted_mobile = format_mobile2(mobile)
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
                FROM messaging2_smswhatsapplog2
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
                FROM messaging2_smswhatsapplog2
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
        sent_at_value = None
        if row[4]:
            try:
                # If the datetime is naive, make it aware using current timezone
                sent_at_value = timezone.localtime(
                    timezone.make_aware(row[4], timezone.utc)  # ← Use timezone.UTC
                ).isoformat()
            except Exception as e:
                print(f"⚠️ Timezone conversion error: {e}")
                sent_at_value = row[4].isoformat() if row[4] else None
        else:
            sent_at_value = None
        messages.append({
            "id": row[0],
            "mobile": row[1],
            "sent_text_message": row[2] or "",
            "message_type": row[3],
           "sent_at": sent_at_value,
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
def get_initial_messages2(mobile):
    """
    Get initial messages - last 7 days only
    """
    mobile = format_mobile2(mobile)
    seven_days_ago = timezone.now() - timedelta(days=7)

    # Get messages from last 7 days
    qs = SmsWhatsAppLog2.objects.filter(
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
        "has_more": SmsWhatsAppLog2.objects.filter(
            mobile=mobile,
            sent_at__lt=seven_days_ago
        ).exists()
    }

@sync_to_async
def create_outgoing_log2(mobile: str, text: str, message_id: str, content_type: str = "text",
                        media_filename: Optional[str] = None, sender_name: str = ""):
    """Create a log for outgoing message"""
    temp_id = message_id or str(uuid.uuid4())
    log = SmsWhatsAppLog2.objects.create(
        customer_name=sender_name, #thus
        mobile=format_mobile2(mobile),
        template_name="manual",
        sent_text_message=text or "",
        status="Pending",
        message_id=temp_id,
        message_type="Sent",
        content_type=content_type,
    )

    ChatContact2.objects.update_or_create(
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
def mark_messages_read_db2(mobile: str):
    """Mark all messages as read for a mobile- DON'T update last_time"""
    updated = SmsWhatsAppLog2.objects.filter(
        mobile=format_mobile2(mobile),
        message_type="Received",
        status="Unread"
    ).update(status="Read")

    ChatContact2.objects.filter(mobile=format_mobile2(mobile)).update(unread=0)
    return updated

@sync_to_async
def update_message_status_in_db2(message_id: str, status: str):
    """Update message status in database"""
    return SmsWhatsAppLog2.objects.filter(message_id=message_id).update(status=status)

# -------------------------
# WhatsApp API Helpers
# -------------------------
def send_whatsapp_text_message2(to_number: str, text_body: str) -> dict:
    """Send text message via WhatsApp API"""
    url = f"https://graph.facebook.com/v22.0/{settings.WHATSAPP2_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {settings.WHATSAPP2_ACCESS_TOKEN}",
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
def get_unread_count2():
    return ChatContact2.objects.filter(unread__gt=0).count()
# -------------------------
# MAIN CONSUMER
# -------------------------
class ChatConsumer2(AsyncJsonWebsocketConsumer):

    async def connect(self):
        """Handle WebSocket connection"""
        print(f"WebSocket connection attempt at {timezone.now()}")

        self.mobile = None
        self.groups_joined = []
        self.connection_active = True

        try:
            await self.accept()
            print(f"WebSocket accepted - Channel: {self.channel_name}")

            await self._add_to_group("delivery_group2")
            await self._add_to_group("global_contacts2")

            path_mobile = self.scope.get("url_route", {}).get("kwargs", {}).get("mobile")
            if path_mobile:
                gm = ws_group_name2(path_mobile)
                if gm:
                    self.mobile = path_mobile
                    await self._add_to_group(f"chat2_{gm}")
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
            size = int(content.get("size", 30))
            q = content.get("q", "")
            filter_type = content.get("filter", "all")
            level = None
            group_ids = None

        # Get the authenticated user from the WebSocket scope (requires AuthMiddlewareStack)
            user = self.scope.get("user")
            if user and user.is_authenticated:
                try:
                    from .models import Agent
                    agent = await sync_to_async(Agent.objects.get)(user=user)
                    if agent.role == 'ADMIN':
                        level = None
                        group_ids = None
                    else:

                        level = agent.level
                # For non‑agent roles (MANAGER, HEAD, EXECUTIVE), fetch group IDs
                        if level != 'ESC1':
                            group_ids = await sync_to_async(lambda: list(agent.groups.values_list('id', flat=True)))()
                except Agent.DoesNotExist:
                    pass
            else:
            # Fallback: try session key (legacy)
                session = self.scope.get("session", {})
                user_id = session.get("messaging2_user")
                if user_id:
                    from django.contrib.auth.models import User
                    try:
                        user = await sync_to_async(User.objects.get)(id=user_id)
                        agent = await sync_to_async(Agent.objects.get)(user=user)
                        if agent.role=='ADMIN':
                            level=None
                            group_ids=None
                        else:
                            level = agent.level
    
                            if level != 'ESC1':
                                group_ids = await sync_to_async(lambda: list(agent.groups.values_list('id', flat=True)))()
                    except Exception:
                        pass

            res = await get_contacts_page2(
            page=page,
            size=size,
            q=q,
            filter_type=filter_type,
            level=level,
            group_ids=group_ids   # ← now correctly passed
        )

            if self.connection_active:
                await self.send_json({
                "type": "contacts.page",
                "contacts": res["contacts"],
                "page": page,
                "total_pages": res["total_pages"],
                "has_more": res["has_more"],
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

            gm = ws_group_name2(mobile)
            if gm:
                if self.mobile:
                    old_gm = ws_group_name2(self.mobile)
                    if old_gm and f"chat2_{old_gm}" in self.groups_joined:
                        await self.channel_layer.group_discard(f"chat2_{old_gm}", self.channel_name)
                        self.groups_joined.remove(f"chat2_{old_gm}")

                self.mobile = mobile
                await self._add_to_group(f"chat2_{gm}")

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


            if not mobile:
                print("❌ No mobile provided")
                return
            # Get messages (first load = last 7 days, then older)
            res = await get_messages_page_from_db2(mobile, before_date,limit)

            if len(res['messages']) > 0:
                pass
            else:
                formatted_mobile = format_mobile2(mobile)
                direct_count = await sync_to_async(SmsWhatsAppLog2.objects.filter(mobile=formatted_mobile).count)()


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

            await mark_messages_read_db2(mobile)

            # gm = ws_group_name2(mobile)

            # if gm:
            #     await self.channel_layer.group_send(
            #         f"chat2_{gm}",
            #         {
            #             "type": "delivery.update",
            #             "message_id": "",
            #             "status": "Read",
            #             "mobile": mobile
            #         }
            #     )

            await self.channel_layer.group_send(
                "global_contacts2",
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
                gm = ws_group_name2(mobile)
                if gm:
                    await self.channel_layer.group_send(
                        f"chat2_{gm}",
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
                sid = self.scope["session"].get("messaging2_user")
                if sid:
                    from django.contrib.auth.models import User
                    u = await sync_to_async(User.objects.filter(id=sid).first)()
                    if u:
                        agent_name = u.username
            except:
                pass

            # Create pending message log
            created = await create_outgoing_log2(mobile, text, "", content_type, sender_name=agent_name or "")
            created["sender_name"] = agent_name

            # Clear cache
            cache.clear()

            # Real-time contact update
            await self.channel_layer.group_send(
                "global_contacts2",
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
            gm = ws_group_name2(mobile)
            if gm and self.connection_active:
                await self.channel_layer.group_send(
                    f"chat2_{gm}",
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
                send_resp = await sync_to_async(send_whatsapp_text_message2)(mobile, text)
                if isinstance(send_resp, dict) and "messages" in send_resp:
                    msg_id = send_resp["messages"][0].get("id", "")
            else:
                print(f"Media message type {content_type} should be sent via API")
                await sync_to_async(
                    lambda: SmsWhatsAppLog2.objects.filter(id=log_id).update(
                        status="Failed",
                        error_message="Media messages must be sent via API endpoint"
                    )
                )()
                return

            print(f"Background send - Message ID from WhatsApp: {msg_id}")

            # Update log with message_id and status
            if msg_id:
                await sync_to_async(
                    lambda: SmsWhatsAppLog2.objects.filter(id=log_id).update(
                        message_id=msg_id,
                        status="Sent"
                    )
                )()

                # Update contact status
                await sync_to_async(
                    lambda: ChatContact2.objects.filter(mobile=mobile).update(
                        last_status="Sent"
                    )
                )()

                gm = ws_group_name2(mobile)
                if gm:
                    print(f"Sending delivery.update to group: chat2_{gm} with status Sent")
                    await self.channel_layer.group_send(
                        f"chat2_{gm}",
                        {
                            "type": "delivery.update",
                            "message_id": msg_id,
                            "status": "Sent",
                            "mobile": mobile
                        }
                    )
            else:
                await sync_to_async(
                    lambda: SmsWhatsAppLog2.objects.filter(id=log_id).update(
                        status="Failed",
                        error_message="No response from WhatsApp"
                    )
                )()

        except Exception as e:
            print(f"WhatsApp send error: {e}")
            traceback.print_exc()
            await sync_to_async(
                lambda: SmsWhatsAppLog2.objects.filter(id=log_id).update(
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
            unread_count = await get_unread_count2()
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
            unread_count = await get_unread_count2()
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
