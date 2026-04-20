# messaging2/consumers.py
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

from .models import SmsWhatsAppLog2
from .utils import format_mobile2

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

def ws_group_name2(mobile: str) -> str:
    return digits_only(mobile)

# -------------------------
# Database Queries
# -------------------------
@sync_to_async
def get_contacts_page2(page=1, size=100, q=""):
    """
    Get contacts with pagination and search - Using SmsWhatsAppLog2
    """
    # First, get distinct mobiles with their latest message time
    mobile_list = SmsWhatsAppLog2.objects.values('mobile').annotate(
        last_time=Max('sent_at')
    ).order_by('-last_time').values_list('mobile', flat=True)[:1000]

    # Then get the actual messages for these mobiles
    contacts = []
    for mobile in mobile_list:
        # Get the latest message for this mobile
        latest_msg = SmsWhatsAppLog2.objects.filter(
            mobile=mobile
        ).order_by('-sent_at').first()

        if latest_msg:
            # Count unread messages
            unread = SmsWhatsAppLog2.objects.filter(
                mobile=mobile,
                message_type='Received',
                status='Unread'
            ).count()

            last_msg = latest_msg.sent_text_message or ""
            last_type = latest_msg.message_type or ""
            last_status = latest_msg.status or ""

            # Media preview
            if latest_msg.content_type in ['image', 'video', 'audio']:
                last_msg = f"[{latest_msg.content_type}]"
            elif latest_msg.content_type == 'document':
                last_msg = "[Document]"

            contacts.append({
                "mobile": format_mobile2(mobile),
                "last_time": latest_msg.sent_at.isoformat() if latest_msg.sent_at else "",
                "last_msg": last_msg[:60],
                "last_type": last_type,
                "last_status": last_status,
                "unread": unread,
            })

    # Apply search filter if needed
    if q:
        q = q.strip()
        digits = re.sub(r"\D", "", q)
        if digits:
            # Filter by mobile digits
            contacts = [c for c in contacts if digits in digits_only(c["mobile"])]
        else:
            # Filter by message text
            contacts = [c for c in contacts if q.lower() in c["last_msg"].lower()]

    # Paginate
    total = len(contacts)
    start = (page - 1) * size
    end = start + size
    page_contacts = contacts[start:end]

    return {
        "contacts": page_contacts,
        "total_pages": (total + size - 1) // size
    }

@sync_to_async
def get_messages_page_from_db2(mobile, page=1, size=30):
    """
    Get messages for a specific mobile with pagination
    """
    mobile_norm = format_mobile2(mobile)

    # Get total count for pagination
    total = SmsWhatsAppLog2.objects.filter(mobile=mobile_norm).count()

    # Get paginated messages
    qs = SmsWhatsAppLog2.objects.filter(
        mobile=mobile_norm
    ).order_by('-sent_at').values(
        'id', 'mobile', 'sent_text_message', 'message_type',
        'sent_at', 'message_id', 'content_type', 'media_file',
        'status', 'customer_name', 'job_id'
    )[(page-1)*size:page*size]

    messages = list(qs)[::-1]  # Reverse to show oldest first

    result = []
    for m in messages:
        media_url = ""
        if m.get('media_file'):
            try:
                media_url = default_storage.url(m['media_file'])
            except:
                pass

        result.append({
            "id": m['id'],
            "mobile": m['mobile'],
            "sent_text_message": m['sent_text_message'] or "",
            "message_type": m['message_type'],
            "sent_at": m['sent_at'].isoformat() if m['sent_at'] else "",
            "message_id": m['message_id'] or "",
            "content_type": m['content_type'] or "text",
            "media_file": media_url,
            "status": m['status'] or "",
            "sender_name": m['customer_name'] or "",
        })

    return {
        "messages": result,
        "total_pages": (total + size - 1) // size
    }

@sync_to_async
def create_outgoing_log2(mobile: str, text: str, message_id: str, content_type: str = "text", media_filename: Optional[str] = None, job_id: str = None):
    """
    Create a log for outgoing message using SmsWhatsAppLog2
    """
    log = SmsWhatsAppLog2.objects.create(
        job_id=job_id,  # ADDED
        customer_name="",
        mobile=format_mobile2(mobile),
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
def mark_messages_read_db2(mobile: str):
    """
    Mark all messages as read for a mobile
    """
    SmsWhatsAppLog2.objects.filter(
        mobile=format_mobile2(mobile),
        message_type="Received",
        status="Unread"
    ).update(status="Read")

# -------------------------
# WhatsApp API Helpers
# -------------------------
def send_text_via_whatsapp2(to_number: str, text_body: str) -> dict:
    """Send text message via WhatsApp API"""
    url = f"https://graph.facebook.com/v17.0/{settings.WHATSAPP2_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {settings.WHATSAPP2_ACCESS_TOKEN}",
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
class Chat2Consumer(AsyncJsonWebsocketConsumer):

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
            await self._add_to_group("delivery_group2")
            await self._add_to_group("contacts_group2")
            await self._add_to_group("presence_group2")
            print("Joined global groups")

            # Check for mobile in path
            path_mobile = self.scope.get("url_route", {}).get("kwargs", {}).get("mobile")
            if path_mobile:
                gm = ws_group_name2(path_mobile)
                if gm:
                    self.mobile = path_mobile
                    await self._add_to_group(f"chat2_{gm}")
                    print(f"Joined chat group for {path_mobile}")

            # Send connected confirmation
            await self.send_json({
                "type": "connected",
                "message": "ws_connected",
                "timestamp": str(timezone.now())
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

            res = await get_contacts_page2(page=page, q=q)

            if self.connection_active:
                await self.send_json({
                    "type": "contacts.page",
                    "contacts": res["contacts"],
                    "page": page,
                    "total_pages": res["total_pages"]
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

            gm = ws_group_name2(mobile)
            if gm:
                # Leave previous chat
                if self.mobile:
                    old_gm = ws_group_name2(self.mobile)
                    if old_gm and f"chat2_{old_gm}" in self.groups_joined:
                        await self.channel_layer.group_discard(f"chat2_{old_gm}", self.channel_name)
                        self.groups_joined.remove(f"chat2_{old_gm}")
                        print(f"Left previous chat: {old_gm}")

                # Join new chat
                self.mobile = mobile
                await self._add_to_group(f"chat2_{gm}")

                # Notify presence
                await self.channel_layer.group_send(
                    "presence_group2",
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
            page = int(content.get("page", 1))
            size = int(content.get("page_size", 30))

            if not mobile:
                return

            res = await get_messages_page_from_db2(mobile, page, size)

            if self.connection_active:
                await self.send_json({
                    "type": "messages.page",
                    "mobile": mobile,
                    "messages": res["messages"],
                    "meta": {
                        "page": page,
                        "total_pages": res["total_pages"]
                    }
                })
        except Exception as e:
            print(f"Error in _handle_get_messages: {e}")
            traceback.print_exc()

    async def _handle_mark_read(self, content):
        """Handle mark as read request"""
        try:
            mobile = content.get("mobile")
            if mobile and self.connection_active:
                await mark_messages_read_db2(mobile)

                gm = ws_group_name2(mobile)
                if gm:
                    await self.channel_layer.group_send(
                        f"chat2_{gm}",
                        {
                            "type": "delivery.update",
                            "message_id": "",
                            "status": "Read",
                            "mobile": mobile
                        }
                    )

                await self.channel_layer.group_send(
                    "contacts_group2",
                    {"type": "presence.update", "mobile": mobile, "status": "updated"}
                )

                if self.connection_active:
                    await self.send_json({"type": "marked_read", "mobile": mobile})
        except Exception as e:
            print(f"Error in _handle_mark_read: {e}")
            traceback.print_exc()

    async def _handle_typing(self, content):
        """Handle typing indicator"""
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
        """Handle send message request"""
        try:
            mobile = content.get("mobile")
            text = content.get("text", "")
            content_type = content.get("content_type", "text")

            if not mobile:
                return

            # Get agent name
            agent_name = None
            try:
                sid = self.scope["session"].get("messaging_user2")
                if sid:
                    from django.contrib.auth.models import User
                    u = await sync_to_async(User.objects.filter(id=sid).first)()
                    if u:
                        agent_name = u.username
            except:
                pass

            # Create optimistic log
            created = await create_outgoing_log2(mobile, text, "", content_type)
            created["sender_name"] = agent_name

            # Show message immediately
            gm = ws_group_name2(mobile)
            if gm and self.connection_active:
                await self.channel_layer.group_send(
                    f"chat2_{gm}",
                    {"type": "new_message", "message": created}
                )

            # Send to WhatsApp in background
            asyncio.create_task(
                self._send_to_whatsapp_background(
                    mobile, text, content_type, created["id"], agent_name
                )
            )

            if self.connection_active:
                await self.send_json({"type": "sent_ok", "local_id": created["id"]})

        except Exception as e:
            print(f"Error in _handle_send_message: {e}")
            traceback.print_exc()

    async def _send_to_whatsapp_background(self, mobile, text, content_type, log_id, agent_name):
        """Send message to WhatsApp in background"""
        try:
            if content_type == "text":
                send_resp = await sync_to_async(send_text_via_whatsapp2)(mobile, text)
            else:
                # For now, just handle text
                send_resp = {"messages": [{"id": ""}]}

            msg_id = ""
            if isinstance(send_resp, dict) and "messages" in send_resp:
                msg_id = send_resp["messages"][0].get("id", "")

            # Update log with message_id
            if msg_id:
                await sync_to_async(
                    lambda: SmsWhatsAppLog2.objects.filter(id=log_id).update(message_id=msg_id)
                )()

                # Update ticks
                await self.channel_layer.group_send(
                    "delivery_group2",
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
