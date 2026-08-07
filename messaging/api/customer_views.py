# messaging2/api/customer_views.py

from rest_framework import status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db.models import Q

from messaging.models import Case, CaseComment
from messaging.api.customer_serializers import (
    CustomerTicketCreateSerializer,
    CustomerTicketDetailSerializer,
    CustomerTicketListSerializer,
    CustomerCommentSerializer,
)
from messaging2.utils import format_mobile2
from adminpanel.views import APP_CONFIG

# ─── Helper to get app from query parameters ───────────────────
def get_app_from_request(request):
    # We keep this for possible other uses, but for case creation we force 'sms'
    return request.query_params.get('app', 'sms') 


# ──────────────────────────────────────────────────────────────────
#  PUBLIC CUSTOMER ENDPOINTS
# ──────────────────────────────────────────────────────────────────

# messaging2/api/customer_views.py

@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def customer_create_ticket(request):
    """
    Create a new ticket – always stored in the unified SMS case table.
    """
    # Force app to 'sms' for case creation
    app = 'sms'   # ✅ hardcoded

    # Get the contact model for this app (SMS)
    config = APP_CONFIG.get(app)
    ContactModel = config.get('contact_model') if config else None

    mutable_data = request.data.copy()
    mutable_data['source_app'] = app   # explicitly set

    serializer = CustomerTicketCreateSerializer(
        data=mutable_data,
        context={'request': request, 'app': app}   # pass 'sms'
    )
    if not serializer.is_valid():
        return Response({'error': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    case = serializer.save()   # uses Case from messaging.models

    # ─── Create/Update ChatContact (SMS app's contact model) ──────────
    if ContactModel:
        mobile = case.mobile
        last_msg = f"📩 Ticket created: {case.case_id}"
        contact, created = ContactModel.objects.get_or_create(
            mobile=mobile, 
            defaults={
                'last_msg': last_msg,
                'last_time': timezone.now(),
                'last_type': 'System',
                'last_status': 'Open',
                'unread': 0,
                'current_level': case.current_level,
            }
        )
        if not created:
            ContactModel.objects.filter(mobile=mobile).update(
                last_msg=last_msg,
                last_time=timezone.now(),
                last_type='System',
                last_status=case.status,
                current_level=case.current_level,
            )

        # WebSocket broadcast (SMS app channel)
        try:
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync
            channel_layer = get_channel_layer()
            channel_group = config.get('channel_group')
            if channel_group:
                async_to_sync(channel_layer.group_send)(
                    channel_group,
                    {
                        "type": "contact.update",
                        "contact": {
                            "mobile": mobile,
                            "last_msg": last_msg,
                            "last_time": timezone.now().isoformat(),
                            "last_type": "System",
                            "last_status": case.status,
                            "current_level": case.current_level,
                            "unread": contact.unread if not created else 0,
                        }
                    }
                )
        except Exception:
            pass

    return Response({
        'success': True,
        'case_id': case.case_id,
        'customer_token': case.customer_token,
        'app': app,
        'message': 'Ticket created successfully! Please save your token for tracking.',
        'tracking_url': f"/customer/tickets/{case.customer_token}/"
    }, status=status.HTTP_201_CREATED)



@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def customer_ticket_detail(request, token):
    """
    Full ticket details including comments and status.
    Token is unique across all apps, so we don't need app parameter.
    """
    case = get_object_or_404(Case, customer_token=token)

    # Mark as viewed
    if not case.customer_viewed_at:
        case.customer_viewed_at = timezone.now()
        case.save(update_fields=['customer_viewed_at'])

    serializer = CustomerTicketDetailSerializer(case)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def customer_ticket_track(request, token):
    """
    Lightweight tracking – status + timeline.
    Token is unique across all apps.
    """
    case = get_object_or_404(Case, customer_token=token)

    logs = case.escalation_logs.all().order_by('created_at')
    timeline = [
        {
            'from': log.from_level,
            'to': log.to_level,
            'reason': log.reason,
            'timestamp': log.created_at.isoformat()
        }
        for log in logs
    ]

    return Response({
        'case_id': case.case_id,
        'status': case.status,
        'current_level': case.current_level,
        'app': case.source_app,   # tell the customer which app this ticket belongs to
        'created_at': case.created_at.isoformat(),
        'updated_at': case.updated_at.isoformat(),
        'resolved_at': case.resolved_at.isoformat() if case.resolved_at else None,
        'closed_at': case.closed_at.isoformat() if case.closed_at else None,
        'resolution_notes': case.resolution_notes,
        'reopen_count': case.reopen_count,
        'timeline': timeline,
        'customer_viewed_at': case.customer_viewed_at.isoformat() if case.customer_viewed_at else None,
    })


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def customer_tickets_by_mobile(request):
    """
    List ALL tickets for a given mobile number.
    Optionally filter by app using ?app= query parameter.
    If no app is given, returns tickets from ALL apps.
    """
    mobile = request.query_params.get('mobile')
    if not mobile:
        return Response({'error': 'mobile parameter required'}, status=status.HTTP_400_BAD_REQUEST)

    mobile = format_mobile2(mobile)
    app_filter = request.query_params.get('app')

    # Base queryset – all cases for this mobile
    queryset = Case.objects.filter(mobile=mobile)

    if app_filter:
        # Filter by source_app if provided
        queryset = queryset.filter(source_app=app_filter)

    cases = queryset.order_by('-created_at')

    if not cases.exists():
        return Response({'tickets': [], 'message': 'No tickets found for this number'})

    serializer = CustomerTicketListSerializer(cases, many=True)
    return Response({
        'tickets': serializer.data,
        'count': cases.count(),
        'app': app_filter or 'all'   # inform the customer which filter was applied
    })


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def customer_add_comment(request, token):
    """
    Add a reply/remark to an existing ticket.
    Token identifies the ticket uniquely.
    """
    case = get_object_or_404(Case, customer_token=token)

    if case.status == 'Closed':
        return Response(
            {'error': 'This ticket is closed. Please reopen it first.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    serializer = CustomerCommentSerializer(
        data=request.data,
        context={'case': case}
    )
    if not serializer.is_valid():
        return Response({'error': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    comment = serializer.save()

    # Auto‑reopen if customer replies to a resolved ticket
    if case.status == 'Resolved':
        case.status = 'Reopened'
        case.reopen_count += 1
        case.reopen_reason = "Customer replied on resolved ticket"
        case.save(update_fields=['status', 'reopen_count', 'reopen_reason'])

    return Response({
        'success': True,
        'comment_id': comment.id,
        'message': 'Comment added successfully!'
    }, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def customer_reopen_ticket(request, token):
    """
    Request to reopen a closed ticket.
    """
    case = get_object_or_404(Case, customer_token=token)

    if case.status != 'Closed':
        return Response(
            {'error': f'Only closed tickets can be reopened. Current status: {case.status}'},
            status=status.HTTP_400_BAD_REQUEST
        )

    reason = request.data.get('reason', 'Customer requested reopening')

    # Reopen – move to ESC1 (Agent level)
    case.status = 'Reopened'
    case.current_level = 'ESC1'
    case.previous_level = 'CLOSED'
    case.reopen_count += 1
    case.reopen_reason = reason
    case.closed_at = None
    case.closed_by = None
    case.closed_reason = None
    case.resolved_at = None
    case.resolved_by = None
    case.resolution_notes = None
    case.resolved_at_level = None
    case.resolved_by_role = None
    case.updated_at = timezone.now()
    case.save()

    CaseComment.objects.create(
        case=case,
        agent_name="Customer",
        comment=f"🔄 Ticket reopened by customer. Reason: {reason}",
        is_internal=False,
    )

    return Response({
        'success': True,
        'message': 'Ticket reopened successfully. An agent will review it shortly.',
        'status': case.status,
        'current_level': case.current_level
    })
