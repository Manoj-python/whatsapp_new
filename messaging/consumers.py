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
from django.db.models import Q, OuterRef, Subquery

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

def ws_group_name(mobile: str) -> str:
    return digits_only(mobile)

# -------------------------
# Database Queries
# -------------------------
from django.db.models import Q, OuterRef, Subquery
from django.core.cache import cache
from .models import ChatContact, Case, SmsWhatsAppLog
import re


from django.db.models import Q, OuterRef, Subquery
from django.core.cache import cache
from .models import ChatContact, Case, SmsWhatsAppLog
from .utils import format_mobile
import re
import logging

logger = logging.getLogger(__name__)

@sync_to_async
def get_contacts_page(page=1, size=30, q="", filter_type="all", level=None,agent=None):
    """
    Returns contacts/cases respecting user role.
    Optimized for speed – uses exact mobile matching and avoids annotations during search.
    """
    # ----- ESC2, ESC3, ESC4: show CASES -----
    if level and level not in ['ESC1', 'ESC5']:
        case_qs = Case.objects.filter(current_level=level).select_related('group', 'subgroup', 'category')

        if agent:
            filters = Q()
            # 1. For each group the agent belongs to
            for group in agent.groups.all():
                group_subgroups = agent.subgroup.filter(group=group)
                if group_subgroups.exists():
                    # Only these subgroups under this group
                    filters |= Q(group=group, subgroup__in=group_subgroups)
                else:
                    # Entire group (no subgroup restriction)
                    filters |= Q(group=group)
            # 2. Also include any subgroups even if their group is not directly assigned
            filters |= Q(subgroup__in=agent.subgroup.all())
            case_qs = case_qs.filter(filters)
        else:
            case_qs = case_qs.none()

        case_qs = case_qs.exclude(status='Closed')

        # ✅ Annotate with ChatContact (still needed for speed)
        cc_subquery = ChatContact.objects.filter(mobile=OuterRef('mobile')).order_by('-last_time')
        case_qs = case_qs.annotate(
            cc_last_msg=Subquery(cc_subquery.values('last_msg')[:1]),
            cc_unread=Subquery(cc_subquery.values('unread')[:1]),
            cc_last_time=Subquery(cc_subquery.values('last_time')[:1]),
        )

        # 🔥 Search: use exact mobile after normalization
        if q:
            raw_q = q.strip()
            # Normalize to the same format as stored (e.g., +919...)
            normalized_mobile = format_mobile(raw_q)  # assume this returns '+91...' if needed
            digits = re.sub(r"\D", "", raw_q)
            filters = Q()
            if normalized_mobile:
                # Exact match is fastest
                filters |= Q(mobile=normalized_mobile)
            if digits:
                # Fallback: if no exact match, try icontains (but this is slower)
                filters |= Q(mobile__icontains=digits)
            filters |= Q(case_id__icontains=raw_q) | Q(customer_name__icontains=raw_q)
            case_qs = case_qs.filter(filters)

        case_qs = case_qs.order_by('-created_at')
        total = case_qs.count()
        start = (page - 1) * size
        end = start + size
        cases = case_qs[start:end]

        contacts = []
        for case in cases:
            contacts.append({
                "mobile": case.mobile,
                "case_id": case.case_id,
                "customer_name": case.customer_name or "",
                "last_msg": case.cc_last_msg or "No messages yet",
                "last_type": "Case",
                "last_status": case.status,
                "unread": case.cc_unread or 0,
                "last_time": (case.cc_last_time or case.created_at).isoformat() if (case.cc_last_time or case.created_at) else None,
                "current_level": case.current_level,
                "group_name": case.group.name if case.group else "",
                "subgroup_name": case.subgroup.name if case.subgroup else "",
                "category_name": case.category.name if case.category else "",
                "category_id": case.category.id if case.category else None,
                "is_case": True,
            })

        total_pages = (total + size - 1) // size if total > 0 else 1
        return {
            "contacts": contacts,
            "total_pages": total_pages,
            "current_page": page,
            "total": total,
            "has_more": page < total_pages,
            "unread_count": 0
        }

    # ----- ESC1 and ESC5: show CONTACTS -----
    # 1) Start with a simple queryset – no annotations yet (will add later if needed)
    base_qs = ChatContact.objects.all()

    if filter_type == "unread":
        base_qs = base_qs.filter(unread__gt=0).exclude(last_msg__icontains="No messages yet").exclude(last_msg="").exclude(last_msg__isnull=True)
    elif filter_type == "assigned":
        base_qs = base_qs.exclude(last_msg__icontains="No messages yet")

    # 2) 🚀 SEARCH – use exact mobile after normalization
    if q:
        raw_q = q.strip()
        normalized_mobile = format_mobile(raw_q)  # e.g., '+919885152879'
        digits = re.sub(r"\D", "", raw_q)

        # Get mobiles from ChatContact that match (fast exact match)
        chat_mobiles = []
        if normalized_mobile:
            chat_mobiles = list(base_qs.filter(mobile=normalized_mobile).values_list('mobile', flat=True))
        if not chat_mobiles and digits:
            # Fallback: use icontains (but only if exact didn't find anything)
            chat_mobiles = list(base_qs.filter(mobile__icontains=digits).values_list('mobile', flat=True))

        # Also get mobiles from Case (even if no ChatContact)
        case_mobiles = []
        if normalized_mobile:
            case_mobiles = list(Case.objects.filter(mobile=normalized_mobile).exclude(status='Closed').values_list('mobile', flat=True).distinct())
        if not case_mobiles and digits:
            case_mobiles = list(Case.objects.filter(mobile__icontains=digits).exclude(status='Closed').values_list('mobile', flat=True).distinct())

        # Combine unique mobiles
        all_mobiles = list(set(chat_mobiles) | set(case_mobiles))

        if not all_mobiles:
            # No matches – return empty list
            return {
                "contacts": [],
                "total_pages": 1,
                "current_page": page,
                "total": 0,
                "has_more": False,
                "unread_count": 0
            }

        # Now fetch ChatContact records for these mobiles (with annotations for display)
        latest_case = Case.objects.filter(mobile=OuterRef('mobile')).order_by('-created_at')
        qs = ChatContact.objects.filter(mobile__in=all_mobiles).annotate(
            latest_group_name=Subquery(latest_case.values('group__name')[:1]),
            latest_subgroup_name=Subquery(latest_case.values('subgroup__name')[:1]),
            latest_category_name=Subquery(latest_case.values('category__name')[:1]),
            latest_category_id=Subquery(latest_case.values('category_id')[:1]),
            latest_customer_name=Subquery(latest_case.values('customer_name')[:1]),
        )
        # Re-apply filter_type if needed (since we fetched extra mobiles from cases, they might not satisfy unread/assigned)
        if filter_type == "unread":
            qs = qs.filter(unread__gt=0).exclude(last_msg__icontains="No messages yet").exclude(last_msg="").exclude(last_msg__isnull=True)
        elif filter_type == "assigned":
            qs = qs.exclude(last_msg__icontains="No messages yet")

        qs = qs.order_by('-last_time')

    else:
        # No search – use the base queryset with annotations for display
        latest_case = Case.objects.filter(mobile=OuterRef('mobile')).order_by('-created_at')
        qs = base_qs.annotate(
            latest_group_name=Subquery(latest_case.values('group__name')[:1]),
            latest_subgroup_name=Subquery(latest_case.values('subgroup__name')[:1]),
            latest_category_name=Subquery(latest_case.values('category__name')[:1]),
            latest_category_id=Subquery(latest_case.values('category_id')[:1]),
        )
        qs = qs.order_by('-last_time')

    # Paginate
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

        contacts.append({
            "mobile": c.mobile,
            "last_msg": last_msg,
            "last_type": c.last_type or "",
            "last_status": c.last_status or "",
            "unread": c.unread,
            "last_time": c.last_time.isoformat() if c.last_time else None,
            "current_level": c.current_level or "ESC1",
            "group_name": c.latest_group_name or "",
            "subgroup_name": c.latest_subgroup_name or "",
            "category_name": c.latest_category_name or "",
            "category_id": c.latest_category_id,
        })

    total_pages = (total + size - 1) // size if total > 0 else 1
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

from datetime import datetime, timedelta
from django.utils import timezone

from django.core.cache import cache
from .utils import format_mobile
from django.core.files.storage import default_storage

def clear_chat_cache(mobile):
    formatted = format_mobile(mobile)

    try:
        cache.delete_pattern(f"chat:{formatted}:*")
        print("🧹 Cache cleared for:", formatted)
    except:
        pass
# ================================
# 🔥 MESSAGE FETCH WITH CACHING
# ================================
@sync_to_async
def get_messages_page_from_db(mobile, before_date=None, limit=30):
    from .utils import format_mobile
    from django.db import connection
    from datetime import datetime
    from django.core.cache import cache
    from django.core.files.storage import default_storage

    formatted_mobile = format_mobile(mobile)
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
                FROM messaging_smswhatsapplog
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
                FROM messaging_smswhatsapplog
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
        "sent_at": timezone.localtime(log.sent_at).isoformat(),
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
            size = int(content.get("size", 30))
            q = content.get("q", "")
            filter_type = content.get("filter", "all")
            level = None
            group_ids = None
            subgroup_ids = None
            agent = None  
            # Get the authenticated user from the WebSocket scope
            user = self.scope.get("user")
            if user and user.is_authenticated:
                try:
                    from messaging2.models import Agent
                    agent = await sync_to_async(Agent.objects.get)(user=user)
                    if agent.role == 'ADMIN':
                        level = None          # ESC5 – sees all contacts (no filter)
                        group_ids = None
                        subgroup_ids = None
                    else:
                        level = agent.level
                        if level != 'ESC1':   # ESC2, ESC3, ESC4 – need permissions
                            group_ids = await sync_to_async(lambda: list(agent.groups.values_list('id', flat=True)))()
                            subgroup_ids = await sync_to_async(lambda: list(agent.subgroup.values_list('id', flat=True)))()
                        # For ESC1 – level remains 'ESC1', group_ids/subgroup_ids remain None → no filter in get_contacts_page2
                except Agent.DoesNotExist:
                    pass
            else:
                # Fallback: try session key (legacy)
                session = self.scope.get("session", {})
                user_id = session.get("messaging_user")
                if user_id:
                    from django.contrib.auth.models import User
                    try:
                        user = await sync_to_async(User.objects.get)(id=user_id)
                        agent = await sync_to_async(Agent.objects.get)(user=user)
                        if agent.role == 'ADMIN':
                            level = None
                            group_ids = None
                            subgroup_ids = None
                        else:
                            level = agent.level
                            if level != 'ESC1':
                                group_ids = await sync_to_async(lambda: list(agent.groups.values_list('id', flat=True)))()
                                subgroup_ids = await sync_to_async(lambda: list(agent.subgroup.values_list('id', flat=True)))()
                    except Exception:
                        pass

            # Debug logging
            print(f"📌 _handle_get_contacts: level={level}, group_ids={group_ids}, subgroup_ids={subgroup_ids}")

            res = await get_contacts_page(
                page=page,
                size=size,
                q=q,
                filter_type=filter_type,
                level=level,
                agent=agent
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
            print(f"❌ Error in _handle_get_contacts: {e}")
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
                print("❌ No mobile provided")
                return
            # Get messages (first load = last 7 days, then older)
            res = await get_messages_page_from_db(mobile, before_date,limit)
           
            if len(res['messages']) > 0:
                pass
            else:
                print(f"   ⚠️ NO MESSAGES FOUND in query result!")
                formatted_mobile = format_mobile(mobile)
                direct_count = await sync_to_async(SmsWhatsAppLog.objects.filter(mobile=formatted_mobile).count)()
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

            await mark_messages_read_db(mobile)

            # gm = ws_group_name(mobile)

            # if gm:
            #     await self.channel_layer.group_send(
            #         f"chat_{gm}",
            #         {
            #             "type": "delivery.update",
            #             "message_id": "",
            #             "status": "Read",
            #             "mobile": mobile
            #         }
            #     )

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
