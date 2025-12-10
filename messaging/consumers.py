
# messaging/consumers.py
import json
import re
from typing import List, Dict, Any, Optional

from channels.generic.websocket import AsyncJsonWebsocketConsumer
from asgiref.sync import sync_to_async
from django.core.paginator import Paginator
from django.conf import settings

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

# WS-safe group name (digits only)
def ws_group_name(mobile: str) -> str:
    return digits_only(mobile)

# -------------------------
# Database helpers (sync -> async)
# -------------------------
@sync_to_async
def get_contacts_from_db(q: str = "") -> List[Dict[str, Any]]:
    """
    Return list of contacts grouped by mobile with:
    - last message time
    - last message text
    - last message type (Sent/Received)
    - last status (for ticks)
    - unread count
    Supports search by number or message text.
    """
    from django.db.models import Max, Count, Q, Subquery, OuterRef

    last_msg_qs = SmsWhatsAppLog.objects.filter(
        mobile=OuterRef("mobile")
    ).order_by("-sent_at")

    qs = (
        SmsWhatsAppLog.objects.values("mobile")
        .annotate(
            last_time=Max("sent_at"),
            last_msg=Subquery(last_msg_qs.values("sent_text_message")[:1]),
            last_type=Subquery(last_msg_qs.values("message_type")[:1]),
            last_status=Subquery(last_msg_qs.values("status")[:1]),
            unread=Count("id", filter=Q(message_type="Received", status="Unread")),
        )
        .order_by("-last_time")
    )

    # Search logic
    if q:
        digits = re.sub(r"\D", "", q)
        if digits:
            qs = qs.filter(mobile__icontains=digits)
        else:
            mobiles_matching = SmsWhatsAppLog.objects.filter(
                sent_text_message__icontains=q
            ).values_list("mobile", flat=True)
            qs = qs.filter(mobile__in=list(mobiles_matching))

    out = []
    for item in qs:
        out.append({
            "mobile": format_mobile(item["mobile"]),
            "last_time": item["last_time"].isoformat() if item["last_time"] else "",
            "last_msg": item["last_msg"] or "",
            "last_type": item["last_type"] or "",
            "last_status": item["last_status"] or "",
            "unread": int(item["unread"]),
        })

    return out
@sync_to_async
def get_messages_page_from_db(mobile: str, page: int = 1, page_size: int = 200):
    """
    Returns messages for mobile ordered by sent_at ascending, paginated.
    page: 1-based indexing, page=1 -> latest messages page
    We will return messages in chronological order (old -> new) for the page.
    Each returned message now includes 'sender_name' (from SmsWhatsAppLog.customer_name).
    """
    normalized = format_mobile(mobile)
    qs = SmsWhatsAppLog.objects.filter(mobile=normalized).order_by("sent_at")
    paginator = Paginator(qs, page_size)

    # normalize requested page into valid range
    page = max(1, int(page))
    page = min(page, paginator.num_pages) if getattr(paginator, "num_pages", 0) else 1
    page_obj = paginator.page(page) if getattr(paginator, "num_pages", 0) else []

    messages = []
    for msg in page_obj:
        media_url = ""
        if msg.media_file:
            try:
                media_url = default_storage.url(msg.media_file.name)
            except Exception:
                media_url = getattr(msg.media_file, "url", "")

        messages.append({
            "id": msg.id,
            "mobile": msg.mobile,
            "sent_text_message": msg.sent_text_message or "",
            "message_type": msg.message_type,
            "sent_at": msg.sent_at.isoformat() if msg.sent_at else "",
            "message_id": msg.message_id or "",
            "content_type": msg.content_type or "text",
            "media_file": media_url,
            "status": msg.status or "",
            "sender_name": msg.customer_name or "",    # ★ include sender_name for history
        })

    meta = {
        "page": page,
        "page_size": page_size,
        "total_pages": paginator.num_pages if hasattr(paginator, "num_pages") else 1,
        "total_items": paginator.count if hasattr(paginator, "count") else len(messages),
    }
    return {"messages": messages, "meta": meta}


@sync_to_async
def create_outgoing_log(mobile: str, text: str, message_id: str, content_type: str="text", media_filename: Optional[str]=None):
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
        # if media_filename points to a temp file path in storage, try to attach (optional)
        try:
            with default_storage.open(media_filename, "rb") as f:
                # save into model field
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
    SmsWhatsAppLog.objects.filter(mobile=format_mobile(mobile), message_type="Received", status="Unread").update(status="Read")


# -------------------------
# WhatsApp Cloud helpers (sync, uses requests)
# If you already have helpers in views.py you can import instead.
# -------------------------
def send_text_via_whatsapp(to_number: str, text_body: str) -> dict:
    url = f"https://graph.facebook.com/v17.0/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}", "Content-Type": "application/json"}
    payload = {"messaging_product":"whatsapp","to": to_number,"type":"text","text":{"body": text_body}}
    r = requests.post(url, headers=headers, json=payload, timeout=30)
    r.raise_for_status()
    return r.json()

def upload_media_via_whatsapp(file_obj) -> dict:
    access_token = settings.WHATSAPP_ACCESS_TOKEN
    phone_number_id = settings.WHATSAPP_PHONE_NUMBER_ID
    url = f"https://graph.facebook.com/v17.0/{phone_number_id}/media"
    headers = {"Authorization": f"Bearer {access_token}"}
    file_obj.seek(0)
    files = {'file': (file_obj.name, file_obj.read(), file_obj.content_type)}
    data = {'messaging_product': 'whatsapp'}
    r = requests.post(url, headers=headers, files=files, data=data, timeout=60)
    r.raise_for_status()
    return r.json()

def send_media_via_whatsapp(to_number: str, media_id: str, media_type: str, caption: str="") -> dict:
    url = f"https://graph.facebook.com/v17.0/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}", "Content-Type": "application/json"}
    payload = {"messaging_product":"whatsapp","to": to_number,"type": media_type, media_type: {"id": media_id}}
    if caption and media_type in ("image","video"):
        payload[media_type]["caption"] = caption
    r = requests.post(url, headers=headers, json=payload, timeout=30)
    r.raise_for_status()
    return r.json()


# -------------------------
# The Consumer
# -------------------------
class ChatConsumer(AsyncJsonWebsocketConsumer):

    async def connect(self):
        # Accept connection
        await self.accept()

        # Subscribe this socket to global groups:
        await self.channel_layer.group_add("delivery_group", self.channel_name)
        await self.channel_layer.group_add("contacts_group", self.channel_name)
        await self.channel_layer.group_add("presence_group", self.channel_name)

        # optional: if mobile provided in ws path (your routing can supply), auto-join that chat group:
        path_mobile = self.scope.get("url_route", {}).get("kwargs", {}).get("mobile")
        if path_mobile:
            gm = ws_group_name(path_mobile)
            if gm:
                self.mobile = path_mobile
                await self.channel_layer.group_add(f"chat_{gm}", self.channel_name)

        # send initial ready message
        await self.send_json({"type":"connected", "message":"ws_connected"})

    async def disconnect(self, close_code):
        # discard per-chat group if present
        if hasattr(self, "mobile"):
            gm = ws_group_name(self.mobile)
            if gm:
                await self.channel_layer.group_discard(f"chat_{gm}", self.channel_name)

        await self.channel_layer.group_discard("delivery_group", self.channel_name)
        await self.channel_layer.group_discard("contacts_group", self.channel_name)
        await self.channel_layer.group_discard("presence_group", self.channel_name)


    # Receive JSON from client
    async def receive_json(self, content, **kwargs):
        t = content.get("type")

        # ---------- CONTACTS ----------
        if t in ("get_contacts", "search_contacts"):
            q = content.get("q", "") or ""
            contacts = await get_contacts_from_db(q)
            await self.send_json({"type":"contacts.list", "contacts": contacts})

        # ---------- JOIN / SUBSCRIBE TO A CHAT ----------
        elif t == "join":
            mobile = content.get("mobile")
            if not mobile:
                await self.send_json({"type":"error", "message":"mobile missing in join"})
                return
            gm = ws_group_name(mobile)
            if gm:
                self.mobile = mobile
                await self.channel_layer.group_add(f"chat_{gm}", self.channel_name)
                # notify presence group
                await self.channel_layer.group_send("presence_group", {"type":"presence.update", "mobile": mobile, "status":"online"})
                await self.send_json({"type":"joined", "mobile": mobile})

        # ---------- GET MESSAGES (page-based) ----------
        elif t == "get_messages":
            mobile = content.get("mobile")
            page = int(content.get("page", 1))
            page_size = int(content.get("page_size", 200))
            if not mobile:
                await self.send_json({"type":"error","message":"mobile required for get_messages"})
                return
            res = await get_messages_page_from_db(mobile, page, page_size)
            # client expects messages in ascending order; include meta for page buttons
            await self.send_json({"type":"messages.page", "mobile": mobile, "messages": res["messages"], "meta": res["meta"]})

        # ---------- MARK READ ----------
        elif t == "mark_read":
            mobile = content.get("mobile")
            if mobile:
                await mark_messages_read_db(mobile)
                # broadcast conversation-level read to chat group
                gm = ws_group_name(mobile)
                if gm:
                    await self.channel_layer.group_send(f"chat_{gm}", {"type":"delivery.update", "message_id":"", "status":"Read", "mobile": mobile})
                # notify contacts group to refresh unread badge
                await self.channel_layer.group_send("contacts_group", {"type":"presence.update", "mobile": mobile, "status":"updated"})
                await self.send_json({"type":"marked_read", "mobile": mobile})

        # ---------- TYPING ----------
        elif t == "typing":
            mobile = content.get("mobile")
            state = content.get("state", False)
            if mobile:
                gm = ws_group_name(mobile)
                if gm:
                    await self.channel_layer.group_send(f"chat_{gm}", {"type":"typing.event", "mobile": mobile, "state": state})

        # ---------- SEND MESSAGE (text) ----------
        elif t == "send_message":
            mobile = content.get("mobile")
            text = content.get("text", "")
            content_type = content.get("content_type", "text")

            if not mobile:
                await self.send_json({"type":"error","message":"mobile required for send_message"})
                return

            # --------------------------------------------
            #  GET LOGGED-IN USERNAME FROM WEBSOCKET SESSION
            # --------------------------------------------
            agent_name = None
            try:
                sid = self.scope["session"].get("messaging_user")
                if sid:
                    from django.contrib.auth.models import User
                    u = await sync_to_async(User.objects.filter(id=sid).first)()
                    if u:
                        agent_name = u.username
            except:
                agent_name = None

            # --------------------------------------------
            #  SEND VIA WHATSAPP CLOUD API
            # --------------------------------------------
            try:
                if content_type == "text":
                    send_resp = await sync_to_async(send_text_via_whatsapp)(mobile, text)
                else:
                    media_id = content.get("media_id", "")
                    media_type = content.get("media_type", "image")
                    send_resp = {}

                    if media_id:
                        send_resp = await sync_to_async(send_media_via_whatsapp)(
                            mobile, media_id, media_type, caption=text
                        )

                msg_id = ""
                if isinstance(send_resp, dict) and "messages" in send_resp:
                    msg_id = send_resp["messages"][0].get("id", "")

            except Exception as e:
                # failed → create DB log with no msg_id
                created = await create_outgoing_log(mobile, text, "", content_type)
                created["sender_name"] = agent_name   # ★ include username

                # broadcast failed msg
                gm = ws_group_name(mobile)
                if gm:
                    await self.channel_layer.group_send(
                        f"chat_{gm}",
                        {"type": "new_message", "message": created}
                    )

                await self.send_json({"type":"send_error","error": str(e)})
                return

            # --------------------------------------------
            #  SAVE & BROADCAST MESSAGE
            # --------------------------------------------
            created = await create_outgoing_log(mobile, text, msg_id, content_type)
            created["sender_name"] = agent_name  # ★ include username

            gm = ws_group_name(mobile)
            if gm:
                await self.channel_layer.group_send(
                    f"chat_{gm}",
                    {"type": "new_message", "message": created}
                )

            # --------------------------------------------
            #  BROADCAST TICKS
            # --------------------------------------------
            await self.channel_layer.group_send(
                "delivery_group",
                {
                    "type": "delivery.update",
                    "message_id": msg_id,
                    "status": "Sent",
                    "mobile": mobile
                }
            )

            await self.send_json({"type": "sent_ok", "message_id": msg_id, "mobile": mobile})


        # ---------- MEDIA PROGRESS (client informs server about upload progress, broadcasts to group) ----------
        elif t == "media.progress":
            mobile = content.get("mobile")
            upload_id = content.get("upload_id")
            progress = content.get("progress", 0)
            filename = content.get("filename", "")
            if mobile and upload_id:
                gm = ws_group_name(mobile)
                if gm:
                    await self.channel_layer.group_send(f"chat_{gm}", {
                        "type": "media.progress",
                        "mobile": mobile,
                        "upload_id": upload_id,
                        "progress": progress,
                        "filename": filename
                    })

        else:
            await self.send_json({"type":"error","message":"unknown type"})

    # --------------------------
    # Handlers for group_send events
    # function names must match dotted message 'type' after replacing '.' with '_'
    # --------------------------
    async def new_message(self, event):
        # forwarded from server-side when new message saved
        await self.send_json({"type":"new.message", "message": event.get("message", {})})

    async def delivery_update(self, event):
        # event: message_id, status, mobile, error
        await self.send_json({
            "type":"delivery.update",
            "message_id": event.get("message_id"),
            "status": event.get("status"),
            "mobile": event.get("mobile",""),
            "error": event.get("error","")
        })

    async def presence_update(self, event):
        await self.send_json({"type":"presence.update","mobile": event.get("mobile"), "status": event.get("status")})

    async def typing_event(self, event):
        await self.send_json({"type":"typing","mobile": event.get("mobile"), "state": event.get("state", False)})

    async def media_progress(self, event):
        await self.send_json({
            "type": "media.progress",
            "mobile": event.get("mobile"),
            "upload_id": event.get("upload_id"),
            "progress": event.get("progress"),
            "filename": event.get("filename",""),
        })

