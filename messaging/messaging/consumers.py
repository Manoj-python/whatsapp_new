# messaging/consumers.py - COMPLETE FIXED VERSION

import json
import re
import asyncio
import traceback
import uuid
from typing import Optional
from datetime import datetime

from channels.generic.websocket import AsyncJsonWebsocketConsumer
from asgiref.sync import sync_to_async
from django.conf import settings
from django.db import close_old_connections
from django.db.models import Q, F
from django.utils import timezone
from django.core.cache import cache

from .models import SmsWhatsAppLog, ChatContact
from .utils import format_mobile

import requests

# -------------------------
# Helpers
# -------------------------
def digits_only(x: str) -> str:
    if not x:
        return ""
    return re.sub(r"\D", "", str(x))

def ws_group_name(mobile: str) -> str:
    return digits_only(mobile)

# -------------------------
# Database Queries
# -------------------------
@sync_to_async
def get_contacts_page(page=1, size=30, q="", filter_type="all", level=None):
    """
    Get contacts with pagination and filtering
    filter_type: 'all', 'unread', 'assigned'
    level: 'ESC1', 'ESC2', 'ESC3', 'ESC4', 'ESC5' - for role-based filtering
    """

    qs = ChatContact.objects.all()

    # Apply role-based level filter FIRST
    if level and level != 'ESC1':
        qs = qs.filter(current_level=level)
    
    # Apply additional filters
    if filter_type == "unread":
        qs = qs.filter(unread__gt=0)
        qs = qs.exclude(last_msg__icontains="No messages yet")
        qs = qs.exclude(last_msg="")
        qs = qs.exclude(last_msg__isnull=True)
    elif filter_type == "assigned":
        if level:
            qs = qs.filter(current_level=level)
        qs = qs.exclude(last_msg__icontains="No messages yet")

    # Search filter
    if q:
        raw_q = q.strip()
        digits = re.sub(r"\D", "", raw_q)

        filters = Q()
        if digits:
            filters |= Q(mobile__icontains=digits)
        filters |= Q(last_msg__icontains=raw_q)
        qs = qs.filter(filters)

    qs = qs.order_by('-last_time')

    total = qs.count()
    start = (page - 1) * size
    end = start + size
    contacts_qs = qs[start:end]

    contacts = []
    for c in contacts_qs:
        last_msg = c.last_msg or ""
        if last_msg == "" or last_msg == "No messages yet":
            latest_msg = SmsWhatsAppLog.objects.filter(mobile=c.mobile).order_by('-sent_at').first()
            if latest_msg:
                last_msg = latest_msg.sent_text_message or "[Media]"
                ChatContact.objects.filter(mobile=c.mobile).update(last_msg=last_msg)
            else:
                if filter_type == "unread":
                    continue
                last_msg = "No messages yet"

        # ✅ Fetch the latest case for this mobile to get the group name
        group_name = None
        latest_case = Case.objects.filter(mobile=c.mobile).order_by('-created_at').first()
        if latest_case and latest_case.group:
            group_name = latest_case.group.name

        contacts.append({
            "mobile": c.mobile,
            "last_msg": last_msg,
            "last_type": c.last_type or "",
            "last_status": c.last_status or "",
            "unread": c.unread,
            "last_time": c.last_time.isoformat() if c.last_time else None,
            "current_level": c.current_level or "ESC1",
            "group_name": group_name,   # 🔥 NEW FIELD
        })

    total_pages = (total + size - 1) // size
    
    # Calculate unread count for agent/admin
    unread_count = 0
    if not level or level == 'ESC1':
        unread_count = ChatContact.objects.filter(
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
# messaging/consumers.py - Update get_messages_page_from_db function

from datetime import datetime, timedelta
from django.utils import timezone

@sync_to_async
def get_messages_page_from_db(mobile, before_date=None, before_id=None, limit=30):
    """
    Get messages with cursor-based pagination
    - First load: last 7 days of messages
    - Then load older messages when scrolling up
    """
    mobile = format_mobile(mobile)
    
    # Base query
    qs = SmsWhatsAppLog.objects.filter(mobile=mobile)
    
    # If no cursor, get messages from last 7 days (WhatsApp behavior)
    if before_date is None and before_id is None:
        seven_days_ago = timezone.now() - timedelta(days=7)
        qs = qs.filter(sent_at__gte=seven_days_ago)
        print(f"📅 Loading last 7 days of messages for {mobile}")
    
    # If scrolling up by date
    elif before_date:
        qs = qs.filter(sent_at__lt=before_date)
    
    # If scrolling up by ID (for older messages)
    elif before_id:
        qs = qs.filter(id__lt=before_id)
    
    # Order by sent_at DESC (newest first for efficient pagination)
    qs = qs.order_by('-sent_at')
    
    # Get limit + 1 to check if more exists
    messages_desc = list(qs[:limit + 1])
    has_more = len(messages_desc) > limit
    messages_desc = messages_desc[:limit]
    
    # Reverse to ASC order for display (oldest first in chat)
    messages_asc = list(reversed(messages_desc))
    
    # Get the oldest date for next cursor
    next_cursor_date = None
    if has_more and messages_desc:
        # Get the oldest message's sent_at for next pagination
        oldest_msg = messages_desc[-1]
        next_cursor_date = oldest_msg.sent_at.isoformat()
    
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
        } for m in messages_asc],
        "has_more": has_more,
        "next_cursor_date": next_cursor_date
    }


@sync_to_async
def get_initial_messages(mobile):
    """
    Get initial messages - last 7 days only
    """
    mobile = format_mobile(mobile)
    seven_days_ago = timezone.now() - timedelta(days=7)
    
    # Get messages from last 7 days
    qs = SmsWhatsAppLog.objects.filter(
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
        "has_more": SmsWhatsAppLog.objects.filter(
            mobile=mobile,
            sent_at__lt=seven_days_ago
        ).exists()
    }

@sync_to_async
def create_outgoing_log(mobile: str, text: str, message_id: str, content_type: str = "text", 
                        media_filename: Optional[str] = None, sender_name: str = ""):
    """Create a log for outgoing message"""
    temp_id = message_id or str(uuid.uuid4())
    log = SmsWhatsAppLog.objects.create(
        customer_name=sender_name,
        mobile=format_mobile(mobile),
        template_name="manual",
        sent_text_message=text or "",
        status="Pending",
        message_id=temp_id,
        message_type="Sent",
        content_type=content_type,
    )
    
    ChatContact.objects.update_or_create(
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
        "sent_at": log.sent_at.isoformat(),
        "message_type": log.message_type,
        "message_id": log.message_id,
        "status": log.status,
        "sender_name": log.customer_name,
    }

@sync_to_async
def mark_messages_read_db(mobile: str):
    """Mark all messages as read for a mobile- DON'T update last_time"""
    updated = SmsWhatsAppLog.objects.filter(
        mobile=format_mobile(mobile),
        message_type="Received",
        status="Unread"
    ).update(status="Read")
    
    ChatContact.objects.filter(mobile=format_mobile(mobile)).update(unread=0)
    return updated

@sync_to_async
def update_message_status_in_db(message_id: str, status: str):
    """Update message status in database"""
    return SmsWhatsAppLog.objects.filter(message_id=message_id).update(status=status)

# -------------------------
# WhatsApp API Helpers
# -------------------------
def send_whatsapp_text_message(to_number: str, text_body: str) -> dict:
    """Send text message via WhatsApp API"""
    url = f"https://graph.facebook.com/v22.0/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}",
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
def get_unread_count():
    return ChatContact.objects.filter(unread__gt=0).count()
# -------------------------
# MAIN CONSUMER
# -------------------------
class ChatConsumer(AsyncJsonWebsocketConsumer):
    
    async def connect(self):
        """Handle WebSocket connection"""
        print(f"WebSocket connection attempt at {timezone.now()}")
        
        self.mobile = None
        self.groups_joined = []
        self.connection_active = True
        
        try:
            await self.accept()
            print(f"WebSocket accepted - Channel: {self.channel_name}")
            
            await self._add_to_group("delivery_group")
            await self._add_to_group("global_contacts")
            
            path_mobile = self.scope.get("url_route", {}).get("kwargs", {}).get("mobile")
            if path_mobile:
                gm = ws_group_name(path_mobile)
                if gm:
                    self.mobile = path_mobile
                    await self._add_to_group(f"chat_{gm}")
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
            
            res = await get_contacts_page(page=page, q=q, filter_type=filter_type)
            
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
            
            gm = ws_group_name(mobile)
            if gm:
                if self.mobile:
                    old_gm = ws_group_name(self.mobile)
                    if old_gm and f"chat_{old_gm}" in self.groups_joined:
                        await self.channel_layer.group_discard(f"chat_{old_gm}", self.channel_name)
                        self.groups_joined.remove(f"chat_{old_gm}")
                
                self.mobile = mobile
                await self._add_to_group(f"chat_{gm}")
                
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
                return
            # Get messages (first load = last 7 days, then older)
            res = await get_messages_page_from_db(mobile, before_date, before_id, limit)
            
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
            
            await mark_messages_read_db(mobile)
            
            gm = ws_group_name(mobile)
            
            if gm:
                await self.channel_layer.group_send(
                    f"chat_{gm}",
                    {
                        "type": "delivery.update",
                        "message_id": "",
                        "status": "Read",
                        "mobile": mobile
                    }
                )
            
            await self.channel_layer.group_send(
                "global_contacts",
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
                gm = ws_group_name(mobile)
                if gm:
                    await self.channel_layer.group_send(
                        f"chat_{gm}",
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
            created = await create_outgoing_log(mobile, text, "", content_type, sender_name=agent_name or "")
            created["sender_name"] = agent_name
            
            # Clear cache
            cache.clear()
            
            # Real-time contact update
            await self.channel_layer.group_send(
                "global_contacts",
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
            gm = ws_group_name(mobile)
            if gm and self.connection_active:
                await self.channel_layer.group_send(
                    f"chat_{gm}",
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
                send_resp = await sync_to_async(send_whatsapp_text_message)(mobile, text)
                if isinstance(send_resp, dict) and "messages" in send_resp:
                    msg_id = send_resp["messages"][0].get("id", "")
            else:
                print(f"Media message type {content_type} should be sent via API")
                await sync_to_async(
                    lambda: SmsWhatsAppLog.objects.filter(id=log_id).update(
                        status="Failed", 
                        error_message="Media messages must be sent via API endpoint"
                    )
                )()
                return
            
            print(f"Background send - Message ID from WhatsApp: {msg_id}")
            
            # Update log with message_id and status
            if msg_id:
                await sync_to_async(
                    lambda: SmsWhatsAppLog.objects.filter(id=log_id).update(
                        message_id=msg_id, 
                        status="Sent"
                    )
                )()
                
                # Update contact status
                await sync_to_async(
                    lambda: ChatContact.objects.filter(mobile=mobile).update(
                        last_status="Sent"
                    )
                )()
                
                gm = ws_group_name(mobile)
                if gm:
                    print(f"Sending delivery.update to group: chat_{gm} with status Sent")
                    await self.channel_layer.group_send(
                        f"chat_{gm}",
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
                    lambda: SmsWhatsAppLog.objects.filter(id=log_id).update(
                        status="Failed", 
                        error_message="No response from WhatsApp"
                    )
                )()
                
        except Exception as e:
            print(f"WhatsApp send error: {e}")
            traceback.print_exc()
            await sync_to_async(
                lambda: SmsWhatsAppLog.objects.filter(id=log_id).update(
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
            unread_count = await get_unread_count()
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
            unread_count = await get_unread_count()
            await self.send_json({
                "type": "unread.update",
                "unread_count": unread_count
        })
