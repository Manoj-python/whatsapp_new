
# messaging/consumers.py
import json
import re
import asyncio
import traceback
from typing import List, Dict, Any, Optional
from datetime import datetime

from channels.generic.websocket import AsyncJsonWebsocketConsumer
from asgiref.sync import sync_to_async
from django.core.paginator import Paginator
from django.conf import settings
from django.db import close_old_connections
from django.db.models import Q, Max, Count, OuterRef, Subquery
from django.utils import timezone

from .models import SmsWhatsAppLog
from .utils import format_mobile

import requests
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

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
# Database Queries - FIXED for MariaDB
# -------------------------
from django.core.cache import cache
import re
from asgiref.sync import sync_to_async

@sync_to_async
def get_contacts_page(page=1, size=30, q=""):
    q = (q or "").strip()

    # 🚫 DO NOT CACHE SEARCH
    use_cache = not q
    cache_key = f"contacts:{page}"

    if use_cache:
        data = cache.get(cache_key)
        if data:
            return data

    qs = ChatContact.objects.only(
        "mobile","last_msg","last_time","last_type","last_status","unread"
    ).order_by("-last_time")

    # 🔍 SEARCH LOGIC
    if q:
        import re
        digits = re.sub(r"\D", "", q)

        if digits:
            qs = qs.filter(mobile__icontains=digits)   # 🔥 FIXED
        else:
            qs = qs.filter(last_msg__icontains=q)

        qs = qs[:50]   # ⚡ fast search (no pagination)

        data = {
            "contacts": [
                {
                    "mobile": c.mobile,
                    "last_msg": c.last_msg or "",
                    "last_type": c.last_type,
                    "last_status": c.last_status,
                    "unread": c.unread,
                    "last_time": c.last_time.isoformat() if c.last_time else None,
                }
                for c in qs
            ],
            "total_pages": 1
        }

        return data   # 🚫 no cache

    # ===== NORMAL CONTACT LIST =====
    total = qs.count()
    qs = qs[(page-1)*size:page*size]

    data = {
        "contacts":[
            {
                "mobile":c.mobile,
                "last_msg":c.last_msg or "",
                "last_type":c.last_type,
                "last_status":c.last_status,
                "unread":c.unread,
                "last_time":c.last_time.isoformat() if c.last_time else None,
            }
            for c in qs
        ],
        "total_pages":(total+size-1)//size
    }

    if use_cache:
        cache.set(cache_key, data, 20)

    return data

@sync_to_async
def get_messages_page_from_db(mobile, last_id=None, size=30):
    mobile = format_mobile(mobile)

    qs = SmsWhatsAppLog.objects.filter(mobile=mobile)

    if last_id:
        qs = qs.filter(id__lt=last_id)

    qs = qs.order_by('-id')[:size]

    messages = list(qs)[::-1]

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
        } for m in messages],
        "has_more": len(messages) == size
    }

@sync_to_async
def create_outgoing_log(mobile: str, text: str, message_id: str, content_type: str="text", media_filename: Optional[str]=None):
    """
    Create a log for outgoing message
    """
    log = SmsWhatsAppLog.objects.create(
        customer_name="",
        mobile=format_mobile(mobile),
        template_name="manual",
        sent_text_message=text or "",
        status="Sent",
        message_id=message_id or "",
        message_type="Sent",
        content_type=content_type,
    )

    if media_filename:
        try:
            with default_storage.open(media_filename, "rb") as f:
                log.media_file.save(media_filename.split("/")[-1], ContentFile(f.read()))
                log.save()
        except Exception:
            pass

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
    }

@sync_to_async
def mark_messages_read_db(mobile: str):
    """
    Mark all messages as read for a mobile
    """
    SmsWhatsAppLog.objects.filter(
        mobile=format_mobile(mobile),
        message_type="Received",
        status="Unread"
    ).update(status="Read")

# -------------------------
# WhatsApp API Helpers
# -------------------------
def send_text_via_whatsapp(to_number: str, text_body: str) -> dict:
    """Send text message via WhatsApp API"""
    url = f"https://graph.facebook.com/v17.0/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "text",
        "text": {"body": text_body}
    }
    r = requests.post(url, headers=headers, json=payload, timeout=10)
    r.raise_for_status()
    return r.json()


# -------------------------
# MAIN CONSUMER
# -------------------------
from .models import *
class ChatConsumer(AsyncJsonWebsocketConsumer):

    async def connect(self):
        """Handle WebSocket connection"""
        print("=" * 50)
        print(f"WebSocket connection attempt at {timezone.now()}")

        # Initialize state
        self.mobile = None
        self.groups_joined = []
        self.connection_active = True
        self.connection_start_time = timezone.now()

        try:
            # Accept the connection
            await self.accept()
            print(f"WebSocket accepted - Channel: {self.channel_name}")

            # Join global groups
            await self._add_to_group("delivery_group")
            await self._add_to_group("global_contacts")
            await self._add_to_group("presence_group")
            print("Joined global groups")

            # Check for mobile in path
            path_mobile = self.scope.get("url_route", {}).get("kwargs", {}).get("mobile")
            if path_mobile:
                gm = ws_group_name(path_mobile)
                if gm:
                    self.mobile = path_mobile
                    await self._add_to_group(f"chat_{gm}")
                    print(f"Joined chat group for {path_mobile}")

            # Send connected confirmation
            await self.send_json({
                "type": "connected",
                "message": "ws_connected",
                "timestamp": timezone.now().isoformat()
            })

            print(f"Connection successful - Duration: {timezone.now() - self.connection_start_time}")

        except Exception as e:
            print(f"ERROR in connect: {e}")
            traceback.print_exc()

    async def _add_to_group(self, group_name):
        """Add to group with tracking"""
        try:
            await self.channel_layer.group_add(group_name, self.channel_name)
            self.groups_joined.append(group_name)
        except Exception as e:
            print(f"Error adding to group {group_name}: {e}")

    async def disconnect(self, close_code):
        """Clean up resources on disconnect"""
        print(f"Disconnecting with code: {close_code} at {timezone.now()}")
        self.connection_active = False

        # Leave all groups
        for group_name in self.groups_joined[:]:
            try:
                await self.channel_layer.group_discard(group_name, self.channel_name)
                print(f"Left group: {group_name}")
            except Exception as e:
                print(f"Error leaving group {group_name}: {e}")

        self.groups_joined.clear()

        # Close database connections
        await sync_to_async(close_old_connections)()
        print(f"Disconnect complete - Duration: {timezone.now() - self.connection_start_time}")

    async def receive_json(self, content, **kwargs):
        """Handle incoming JSON messages"""
        if not self.connection_active:
            print("Received message but connection inactive, ignoring")
            return

        t = content.get("type")
        print(f"Received message type: {t}")

        # Route to appropriate handler
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
        """Handle contacts request"""
        try:
            page = int(content.get("page", 1))
            q = content.get("q", "") or ""

            res = await get_contacts_page(page=page, q=q)

            if self.connection_active:
                await self.send_json({
                    "type": "contacts.page",
                    "contacts": res["contacts"],
                    "page": page,
                    "has_more": page < res["total_pages"] ,
                })
        except Exception as e:
            print(f"Error in _handle_get_contacts: {e}")
            traceback.print_exc()
            if self.connection_active:
                await self.send_json({"type": "error", "message": str(e)})

    async def _handle_join(self, content):
        """Handle join chat request"""
        try:
            mobile = content.get("mobile")
            if not mobile:
                return

            gm = ws_group_name(mobile)
            if gm:
                # Leave previous chat
                if self.mobile:
                    old_gm = ws_group_name(self.mobile)
                    if old_gm and f"chat_{old_gm}" in self.groups_joined:
                        await self.channel_layer.group_discard(f"chat_{old_gm}", self.channel_name)
                        self.groups_joined.remove(f"chat_{old_gm}")
                        print(f"Left previous chat: {old_gm}")

                # Join new chat
                self.mobile = mobile
                await self._add_to_group(f"chat_{gm}")

                # Notify presence
                await self.channel_layer.group_send(
                    "presence_group",
                    {"type": "presence.update", "mobile": mobile, "status": "online"}
                )

                if self.connection_active:
                    await self.send_json({"type": "joined", "mobile": mobile})
        except Exception as e:
            print(f"Error in _handle_join: {e}")
            traceback.print_exc()

    async def _handle_get_messages(self, content):
        """Handle get messages request"""
        try:
            mobile = content.get("mobile")
            # page = int(content.get("page", 1))
            # size = int(content.get("page_size", 30))
            last_id = content.get("last_id")
            if not mobile:
                return

            res = await get_messages_page_from_db(mobile, last_id)

            if self.connection_active:
                await self.send_json({
                    "type": "messages.page",
                    "mobile": mobile,
                    "messages": res["messages"],
                    "has_more": res["has_more"],
                    # "is_search": res["is_search"] 
                })
        except Exception as e:
            print(f"Error in _handle_get_messages: {e}")
            traceback.print_exc()

    async def _handle_mark_read(self, content):
        """Handle mark as read request"""
        try:
            mobile = content.get("mobile")
            if not mobile or not self.connection_active:
                return

        # ===== 1️⃣ MARK MESSAGES READ =====
            await mark_messages_read_db(mobile)

        # ===== 2️⃣ UPDATE CONTACT TABLE =====
            from django.utils import timezone
            from django.core.cache import cache
            from .models import ChatContact

            await sync_to_async(ChatContact.objects.filter(mobile=mobile).update)(
            unread=0,
            last_status="Read",
            last_time=timezone.now()
        )

        # 🔥 CLEAR CACHE (IMPORTANT)
            cache.clear()

            gm = ws_group_name(mobile)

        # ===== 3️⃣ UPDATE CHAT TICKS =====
            if gm:
                await self.channel_layer.group_send(
                    f"chat_{gm}",
                {
                    "type": "delivery.update",
                    "message_id": "",   # means all messages
                    "status": "Read",
                    "mobile": mobile
                }
            )

        # ===== 4️⃣ 🔥 UPDATE CONTACT LIST (FIXED) =====
            await self.channel_layer.group_send(
                "global_contacts",
            {
                "type": "contact.update",   # ✅ FIXED (NOT presence.update)
                "contact": {
                    "mobile": mobile,
                    "unread": 0,
                    "last_status": "Read",
                    "last_time": timezone.now().isoformat()
                }
            }
        )

        # ===== 5️⃣ ACK =====
            if self.connection_active:
                await self.send_json({
                "type": "marked_read",
                "mobile": mobile
            })

        except Exception as e:
            print(f"Error in _handle_mark_read: {e}")
            traceback.print_exc()

    async def _handle_typing(self, content):
        """Handle typing indicator"""
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
        """Handle send message request"""
        try:
            mobile = content.get("mobile")
            text = content.get("text", "")
            content_type = content.get("content_type", "text")

            if not mobile:
                return

        # ===== GET AGENT NAME =====
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

        # ===== CREATE MESSAGE (ONLY ONCE) =====
            created = await create_outgoing_log(mobile, text, "", content_type)
            created["sender_name"] = agent_name

        # ===== 🔥 UPDATE CONTACT TABLE =====
            from django.utils import timezone
            from .models import ChatContact

            await sync_to_async(ChatContact.objects.update_or_create)(
                mobile=mobile,
                defaults={
                "last_time": timezone.now(),
                "last_msg": text or "",
                "last_type": "Sent",
                "last_status": "Sent",
            }
        )   
             # ===== 🔥 CLEAR CACHE (IMPORTANT) =====
            cache.clear()

        # ===== 🔥 REAL-TIME CONTACT UPDATE =====
            await self.channel_layer.group_send(
                "global_contacts",
            {
                "type": "contact.update",
                "contact": {
                    "mobile": mobile,
                    "last_msg": text or "",
                    "last_time": timezone.now().isoformat(),
                    "last_type": "Sent",
                    "last_status": "Sent",
                    "unread": 0
                }
            }
        )

        # ===== SHOW MESSAGE IN CHAT =====
            gm = ws_group_name(mobile)
            if gm and self.connection_active:
                await self.channel_layer.group_send(
                f"chat_{gm}",
                {"type": "new_message", "message": created}
            )

        # ===== SEND TO WHATSAPP (BACKGROUND) =====
            asyncio.create_task(
                self._send_to_whatsapp_background(
                mobile, text, content_type, created["id"], agent_name
            )
        )

        # ===== ACK =====
            if self.connection_active:
                await self.send_json({
                "type": "sent_ok",
                "local_id": created["id"]
            })

        except Exception as e:
            print(f"Error in _handle_send_message: {e}")
            traceback.print_exc()

    async def _send_to_whatsapp_background(self, mobile, text, content_type, log_id, agent_name):
        """Send message to WhatsApp in background"""
        try:
            if content_type == "text":
                send_resp = await sync_to_async(send_text_via_whatsapp)(mobile, text)
            else:
                # For now, just handle text
                send_resp = {"messages": [{"id": ""}]}

            msg_id = ""
            if isinstance(send_resp, dict) and "messages" in send_resp:
                msg_id = send_resp["messages"][0].get("id", "")

            # Update log with message_id
            if msg_id:
                await sync_to_async(
                    lambda: SmsWhatsAppLog.objects.filter(id=log_id).update(message_id=msg_id)
                )()

                # Update ticks
                await self.channel_layer.group_send(
                    "delivery_group",
                    {
                        "type": "delivery.update",
                        "message_id": msg_id,
                        "status": "Sent",
                        "mobile": mobile
                    }
                )

        except Exception as e:
            print(f"WhatsApp send error: {e}")
            # Update log with error
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
        """Handle new message event"""
        if self.connection_active:
            await self.send_json({
                "type": "new.message",
                "message": event.get("message", {})
            })

    async def delivery_update(self, event):
        """Handle delivery update event"""
        if self.connection_active:
            await self.send_json({
                "type": "delivery.update",
                "message_id": event.get("message_id"),
                "status": event.get("status"),
                "mobile": event.get("mobile", ""),
            })

    async def presence_update(self, event):
        """Handle presence update event"""
        if self.connection_active:
            await self.send_json({
                "type": "presence.update",
                "mobile": event.get("mobile"),
                "status": event.get("status")
            })

    async def typing_event(self, event):
        """Handle typing event"""
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
            "contact": event["contact"]
        })
