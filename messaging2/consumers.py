# messaging2/consumers.py
import json
import uuid
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from asgiref.sync import async_to_sync
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from .models import SmsWhatsAppLog2
from .utils import format_mobile2


class Chat2Consumer(AsyncWebsocketConsumer):

    async def connect(self):
        raw_mobile = self.scope["url_route"]["kwargs"].get("mobile", "")
        self.mobile = format_mobile2(raw_mobile)
        self.group_name = f"chat2_{self.mobile}"

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.channel_layer.group_add("presence_group2", self.channel_name)
        await self.channel_layer.group_add("delivery_group2", self.channel_name)

        await self.accept()

        await self.channel_layer.group_send(
            "presence_group2",
            {"type": "presence.update", "mobile": self.mobile, "status": "online"}
        )

    async def disconnect(self, close_code):
        await self.channel_layer.group_send(
            "presence_group2",
            {"type": "presence.update", "mobile": self.mobile, "status": "offline"}
        )
        await self.channel_layer.group_discard(self.group_name, self.channel_name)
        await self.channel_layer.group_discard("presence_group2", self.channel_name)
        await self.channel_layer.group_discard("delivery_group2", self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        try:
            data = json.loads(text_data or "{}")
        except:
            return

        event_type = data.get("type")

        # typing indicator
        if event_type == "typing":
            await self.channel_layer.group_send(
                self.group_name,
                {
                    "type": "typing.event",
                    "mobile": self.mobile,
                    "typing": data.get("typing")
                }
            )
            return

        # mark read
        if event_type == "mark_read":
            mob = format_mobile2(data.get("mobile", self.mobile))
            await self._mark_read_and_broadcast(mob)
            return

        # sending a message (with or without media)
        if event_type == "message":
            text = data.get("text", "")
            media_meta = data.get("media")

            saved = await self._save_message_with_tempid(
                mobile=self.mobile,
                text=text,
                media_meta=media_meta
            )

            await self.channel_layer.group_send(
                self.group_name,
                {
                    "type": "chat.message",
                    "message_type": "Sent",
                    "mobile": self.mobile,
                    "text": text,
                    "media": saved["media_url"],
                    "content_type": saved["content_type"],
                    "sent_at": saved["sent_at"],
                    "message_id": saved["message_id"],
                    "status": "Pending"
                }
            )
            return

    # EVENT HANDLERS (WS -> UI)

    async def chat_message(self, event):
        await self.send(json.dumps({
            "type": "message",
            "message_type": event["message_type"],
            "mobile": event["mobile"],
            "text": event["text"],
            "media": event["media"],
            "content_type": event["content_type"],
            "sent_at": event["sent_at"],
            "message_id": event["message_id"],
            "status": event.get("status", "Sent")
        }))

    async def typing_event(self, event):
        await self.send(json.dumps({
            "type": "typing",
            "mobile": event["mobile"],
            "typing": event["typing"]
        }))

    async def presence_update(self, event):
        await self.send(json.dumps({
            "type": "presence",
            "mobile": event["mobile"],
            "status": event["status"]
        }))

    async def delivery_update(self, event):
        await self.send(json.dumps({
            "type": "delivery",
            "message_id": event["message_id"],
            "status": event["status"],
            "error": event.get("error", "")
        }))

    # DB HELPERS

    @database_sync_to_async
    def _save_message_with_tempid(self, mobile, text, media_meta):
        tmp_id = f"tmp-{uuid.uuid4().hex}"
        content_type = "text"
        media_url = None
        path = None

        # MEDIA SAVING IF ATTACHED
        if media_meta:
            try:
                filename = media_meta.get("name")
                raw = ContentFile(media_meta["data"].encode("latin1"))
                ct = media_meta.get("content_type", "")
                path = f"whatsapp2_media/{tmp_id}_{filename}"
                default_storage.save(path, raw)
                media_url = default_storage.url(path)
                if ct.startswith("image/"):
                    content_type = "image"
                elif ct.startswith("video/"):
                    content_type = "video"
                elif ct.startswith("audio/"):
                    content_type = "audio"
                else:
                    content_type = "document"
            except:
                pass

        log = SmsWhatsAppLog2.objects.create(
            mobile=mobile,
            customer_name="",
            template_name="manual",
            sent_text_message=text,
            status="Pending",
            message_id=tmp_id,
            message_type="Sent",
            content_type=content_type,
        )

        if path:
            log.media_file.name = path
            log.save()

        return {
            "media_url": media_url,
            "content_type": content_type,
            "sent_at": log.sent_at.isoformat(),
            "message_id": tmp_id
        }

    @database_sync_to_async
    def _mark_read_and_broadcast(self, mobile):
        SmsWhatsAppLog2.objects.filter(
            mobile=mobile, message_type="Received", status="Unread"
        ).update(status="Read")

        async_to_sync(self.channel_layer.group_send)(
            f"chat2_{mobile}",
            {
                "type": "delivery.update",
                "message_id": "",
                "status": "Read",
            }
        )

        return True
