# ============================================
# IMPORTS
# ============================================
import json
import csv
from datetime import datetime, timedelta

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User, Group
from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.core.paginator import Paginator
from django.http import HttpResponse, JsonResponse, Http404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from .models import *
# Models from three apps
from messaging2.models import Agent, Case as psfCase, ChatContact2, SmsWhatsAppLog2
from messaging.models import Case as smsCase, ChatContact, SmsWhatsAppLog
from special_cases.models import Case as SplCase, SmsWhatsAppLog3, ChatContact3

# ============================================
# APP CONFIGURATION
# ============================================
APP_CONFIG = {
    'psf': {
        'name': 'PSF',
        'case_model': psfCase,
        'log_model': SmsWhatsAppLog2,
        'contact_model': ChatContact2,
        'channel_group': 'global_contacts2',
    },
    'sms': {
        'name': 'SMS',
        'case_model': smsCase,
        'log_model': SmsWhatsAppLog,
        'contact_model': ChatContact,
        'channel_group': 'global_contacts',
    },
    'spl': {
        'name': 'SPL Cases',
        'case_model': SplCase,
        'log_model': SmsWhatsAppLog3,
        'contact_model': ChatContact3,
        'channel_group': 'global_contacts3',
    },
}

# ============================================
# HELPER FUNCTIONS
# ============================================
def get_role_display_name(role):
    role_names = {
        'AGENT': '🟢 Normal Agent (ESC1)',
        'LEGAL': '⚖️ Legal Team (ESC2)',
        'LEAD': '⭐ Team Lead (ESC3)',
        'MANAGER': '📊 Manager (ESC4)',
        'ADMIN': '🔒 Administrator (ESC5)',
    }
    return role_names.get(role, role)


def get_agent_from_user(user):
    """Get or create agent profile for user (uses messaging2.Agent)"""
    try:
        return Agent.objects.get(user=user)
    except Agent.DoesNotExist:
        role = 'ADMIN' if user.is_superuser else 'AGENT'
        agent = Agent.objects.create(
            user=user,
            agent_id=f"AGT-{user.id}",
            name=user.get_full_name() or user.username,
            email=user.email or f"{user.username}@example.com",
            role=role,
            is_active=True
        )
        return agent


def get_app_from_request(request):
    """Extract app key from GET parameter, default to 'psf'"""
    app = request.GET.get('app', 'psf')
    if app not in APP_CONFIG:
        app = 'psf'
    return app

from messaging2.views import auto_assign
import uuid 
@csrf_exempt
def create_case_from_chat_api2(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        data = json.loads(request.body)
        mobile = data.get('mobile', '')
        customer_name = data.get('customer_name') or mobile
        agent_name = data.get('agent_name', 'Agent')
        issue_description = data.get('issue_description', '')
        loan_number = data.get('loan_number', '')
        group_name = data.get('group', 'Collections')
        escalate_to = data.get('escalate_to', None)
        force_new = data.get('force_new', False)   # frontend flag

        CaseModel, ContactModel, _, _ = get_app_from_request(request)
        group_obj = SupportGroup.objects.filter(name=group_name).first()
        if not group_obj:
            return JsonResponse({'error': 'Invalid group'}, status=400)

        # Check existing cases (optional, for information)
        existing_case = CaseModel.objects.filter(
            mobile=mobile,
            status__in=['Open', 'In Progress', 'Resolved']
        ).first()

        # If force_new is False and an existing case exists, return it with a flag
        if not force_new and existing_case:
            return JsonResponse({
                'success': True,
                'case': {
                    'case_id': existing_case.case_id,
                    'customer_name': existing_case.customer_name,
                    'assigned_to_name': existing_case.assigned_to_name or 'Unassigned',
                    'current_level': existing_case.current_level,
                    'status': existing_case.status,
                },
                'existing': True,
                'message': 'An active case already exists. Create new anyway?'
            })

        # Determine initial level
        initial_level = 'ESC1'
        if escalate_to and escalate_to.startswith('ESC') and escalate_to != 'ESC1':
            initial_level = escalate_to

        # Create new case
        case_id = f"CASE-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
        case = CaseModel.objects.create(
            case_id=case_id,
            customer_name=customer_name,
            mobile=mobile,
            loan_number=loan_number,
            issue_description=issue_description[:500],
            source='WhatsApp',
            current_level=initial_level,
            status='Open',
            priority='Medium',
            created_by=agent_name,
            group=group_obj,
            assigned_to=None,
            assigned_to_name=None,
        )

        # Auto-assign only for ESC1
        if initial_level == 'ESC1':
            auto_assign(case)
            if case.assigned_to:
                case.assigned_to_name = case.assigned_to.name
                case.save(update_fields=['assigned_to_name'])
        else:
            # Log escalation from ESC1 to target level
            from .models import CaseEscalationLog
            CaseEscalationLog.objects.create(
                case=case,
                from_level='ESC1',
                to_level=initial_level,
                escalated_by=agent_name,
                reason='Created directly at this level'
            )
            ContactModel.objects.update_or_create(
                mobile=mobile,
                defaults={'current_level': initial_level}
            )

        ContactModel.objects.update_or_create(
            mobile=mobile,
            defaults={'current_level': case.current_level}
        )

        return JsonResponse({
            'success': True,
            'case': {
                'case_id': case.case_id,
                'customer_name': case.customer_name,
                'loan_number': case.loan_number,
                'assigned_to_name': case.assigned_to_name or 'Unassigned',
                'current_level': case.current_level,
                'status': case.status,
            },
            'existing': False
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

# ============================================
# AUTHENTICATION VIEWS
# ============================================

def login_view(request):
    if request.method == "POST":
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            request.session["messaging_user"] = user.id
            request.session["messaging2_user"] = user.id
            request.session["messaging3_user"] = user.id

            agent = get_agent_from_user(user)
            if agent.role == 'ADMIN':
                return redirect('admin_dashboard')
            elif agent.role == 'MANAGER':
                return redirect('manager_dashboard')
            elif agent.role == 'EXECUTIVE':
                return redirect('executive_dashboard')
            elif agent.role == 'HEAD':
                return redirect('head_dashboard')
            # LEGAL removed
            else:
                return redirect('agent_dashboard')
        else:
            messages.error(request, "Invalid login")
    return render(request, 'adminpanel/login.html')


def logout_view(request):
    logout(request)
    return redirect('admin_login')


# views.py

@login_required
def create_group(request):
    agent = get_agent_from_user(request.user)

    if agent.role != 'ADMIN':
        messages.error(request, "Access denied")
        return redirect('agent_dashboard')

    if request.method == "POST":
        name = request.POST.get('name')

        if SupportGroup.objects.filter(name=name).exists():
            messages.error(request, "Group already exists")
        else:
            SupportGroup.objects.create(name=name)
            messages.success(request, "Group created successfully")
            return HttpResponse('created')

    return render(request, 'adminpanel/create_group.html')


# ============================================
# UNIFIED ADMIN DASHBOARD (supports ?app=...)
# ============================================
@login_required
def dashboard(request):
    agent = get_agent_from_user(request.user)
    if agent.role != 'ADMIN':
        if agent.role == 'MANAGER':
            return redirect('manager_dashboard')
        elif agent.role == 'LEAD':
            return redirect('lead_dashboard')
        elif agent.role == 'LEGAL':
            return redirect('legal_dashboard')
        else:
            return redirect('agent_dashboard')

    app_key = get_app_from_request(request)
    cfg = APP_CONFIG[app_key]
    CaseModel = cfg['case_model']

    stats = {
        'total_cases': CaseModel.objects.count(),
        'open_cases': CaseModel.objects.filter(status='Open').count(),
        'in_progress_cases': CaseModel.objects.filter(status='In Progress').count(),
        'resolved_cases': CaseModel.objects.filter(status='Resolved').count(),
        'closed_cases': CaseModel.objects.filter(status='Closed').count(),
        'reopened_cases': CaseModel.objects.filter(status='Reopened').count(),
        'esc1': CaseModel.objects.filter(current_level='ESC1').count(),
        'esc2': CaseModel.objects.filter(current_level='ESC2').count(),
        'esc3': CaseModel.objects.filter(current_level='ESC3').count(),
        'esc4': CaseModel.objects.filter(current_level='ESC4').count(),
        'esc5': CaseModel.objects.filter(current_level='ESC5').count(),
        'total_agents': Agent.objects.filter(is_active=True).count(),
    }

    users = User.objects.all().order_by('id')
    users_with_agents = []
    for user in users:
        try:
            user_agent = Agent.objects.get(user=user)
        except Agent.DoesNotExist:
            user_agent = None
        users_with_agents.append({'user': user, 'agent': user_agent})

    context = {
        'users': users,
        'users_with_agents': users_with_agents,
        'stats': stats,
        'current_agent': agent,
        'current_app': app_key,
        'app_name': cfg['name'],
        'app_list': [(key, cfg['name']) for key, cfg in APP_CONFIG.items()],
    }
    return render(request, 'adminpanel/dashboard.html', context)


# ============================================
# API ENDPOINTS (app-aware)
# ============================================

# NEW: Global stats for admin dashboard
@login_required
def get_stats_api(request):
    """Return global case counts and agent count"""
    app_key = get_app_from_request(request)
    CaseModel = APP_CONFIG[app_key]['case_model']
    return JsonResponse({
        'total_cases': CaseModel.objects.count(),
        'open_cases': CaseModel.objects.filter(status='Open').count(),
        'in_progress_cases': CaseModel.objects.filter(status='In Progress').count(),
        'resolved_cases': CaseModel.objects.filter(status='Resolved').count(),
        'closed_cases': CaseModel.objects.filter(status='Closed').count(),
        'total_agents': Agent.objects.filter(is_active=True).count(),
    })

# NEW: Department-wise case counts
@login_required
def get_department_stats_api(request):
    """Return case counts per department (group)"""
    app_key = get_app_from_request(request)
    CaseModel = APP_CONFIG[app_key]['case_model']
    groups = SupportGroup.objects.all()
    dept_stats = []
    total_all = CaseModel.objects.count()
    for group in groups:
        count = CaseModel.objects.filter(group=group).count()
        dept_stats.append({'name': group.name, 'count': count})
    return JsonResponse({'departments': dept_stats, 'total_all': total_all})

# NEW: Enhanced case listing with filters (status, level, department)
@login_required
def get_filtered_cases_api(request):
    """Return cases with optional filters: ?status=, ?level=, ?department="""
    app_key = get_app_from_request(request)
    CaseModel = APP_CONFIG[app_key]['case_model']
    queryset = CaseModel.objects.select_related('group').all().order_by('-created_at')
    
    status = request.GET.get('status')
    if status:
        queryset = queryset.filter(status=status)
    
    level = request.GET.get('level')
    if level:
        queryset = queryset.filter(current_level=level)
    
    department = request.GET.get('department')
    if department and department != 'all':
        queryset = queryset.filter(group__name=department)
    
    cases = queryset[:200]  # limit for performance
    
    case_list = [{
        'case_id': c.case_id,
        'customer_name': c.customer_name,
        'mobile': c.mobile,
        'loan_number': c.loan_number,
        'group_name': c.group.name if c.group else None,
        'priority': c.priority,
        'current_level': c.current_level,
        'status': c.status,
        'created_at': c.created_at.isoformat(),
    } for c in cases]
    
    return JsonResponse({'success': True, 'cases': case_list})

# Keep original endpoints for backward compatibility
@login_required
def search_cases_api(request):
    app_key = get_app_from_request(request)
    CaseModel = APP_CONFIG[app_key]['case_model']
    query = request.GET.get('q', '').strip()
    if not query:
        return JsonResponse({'success': False, 'error': 'No search query provided'})
    cases = CaseModel.objects.filter(
        Q(case_id__icontains=query) | Q(loan_number__icontains=query)
    ).order_by('-created_at')
    cases_data = [{
        'case_id': c.case_id,
        'customer_name': c.customer_name,
        'mobile': c.mobile,
        'loan_number': c.loan_number,
        'status': c.status,
        'priority': c.priority,
        'created_at': c.created_at.isoformat(),
        'current_level': c.current_level,
    } for c in cases]
    return JsonResponse({'success': True, 'cases': cases_data, 'count': len(cases_data)})


def get_level_distribution_api(request):
    app_key = get_app_from_request(request)
    CaseModel = APP_CONFIG[app_key]['case_model']
    data = {
        'esc1': CaseModel.objects.filter(current_level='ESC1').count(),
        'esc2': CaseModel.objects.filter(current_level='ESC2').count(),
        'esc3': CaseModel.objects.filter(current_level='ESC3').count(),
        'esc4': CaseModel.objects.filter(current_level='ESC4').count(),
        'esc5': CaseModel.objects.filter(current_level='ESC5').count(),
        'resolved': CaseModel.objects.filter(current_level='RESOLVED').count(),
        'closed': CaseModel.objects.filter(current_level='CLOSED').count(),
    }
    return JsonResponse(data)


def get_weekly_trend_api(request):
    app_key = get_app_from_request(request)
    CaseModel = APP_CONFIG[app_key]['case_model']
    labels = []
    new_cases = []
    resolved = []
    for i in range(6, -1, -1):
        date = timezone.now().date() - timedelta(days=i)
        labels.append(date.strftime('%a, %b %d'))
        start_of_day = timezone.make_aware(datetime.combine(date, datetime.min.time()))
        end_of_day = start_of_day + timedelta(days=1)
        new_cases.append(CaseModel.objects.filter(created_at__gte=start_of_day, created_at__lt=end_of_day).count())
        resolved.append(CaseModel.objects.filter(resolved_at__gte=start_of_day, resolved_at__lt=end_of_day).count())
    return JsonResponse({'labels': labels, 'new_cases': new_cases, 'resolved': resolved})


def get_open_cases_api(request):
    app_key = get_app_from_request(request)
    CaseModel = APP_CONFIG[app_key]['case_model']
    cases = CaseModel.objects.filter(status__in=['Open', 'In Progress']).order_by('-priority', '-created_at')[:50]
    return JsonResponse({
        'success': True,
        'cases': [{
            'case_id': c.case_id,
            'customer_name': c.customer_name,
            'loan_number': c.loan_number,
            'mobile': c.mobile,
            'priority': c.priority,
            'current_level': c.current_level,
            'status': c.status,
            'created_at': timezone.localtime(c.created_at).isoformat(),
            'group_name': c.group.name if c.group else None,
        } for c in cases]
    })


def get_resolved_cases_api(request):
    app_key = get_app_from_request(request)
    CaseModel = APP_CONFIG[app_key]['case_model']
    cases = CaseModel.objects.filter(status='Resolved').order_by('-resolved_at')[:50]
    return JsonResponse({
        'success': True,
        'cases': [{
            'case_id': c.case_id,
            'customer_name': c.customer_name,
            'loan_number': c.loan_number,
            'mobile': c.mobile,
            'priority': c.priority,
            'current_level': c.current_level,
            'status': c.status,
            'created_at': timezone.localtime(c.created_at).isoformat(),
            'group_name': c.group.name if c.group else None,
        } for c in cases]
    })


def get_closed_cases_api(request):
    app_key = get_app_from_request(request)
    CaseModel = APP_CONFIG[app_key]['case_model']
    cases = CaseModel.objects.filter(status='Closed').order_by('-closed_at')[:50]
    return JsonResponse({
        'success': True,
        'cases': [{
            'case_id': c.case_id,
            'customer_name': c.customer_name,
            'loan_number': c.loan_number,
            'mobile': c.mobile,
            'priority': c.priority,
            'current_level': c.current_level,
            'status': c.status,
            'created_at': timezone.localtime(c.created_at).isoformat(),
            'group_name': c.group.name if c.group else None,
        } for c in cases]
    })


def get_esc5_cases_api(request):
    app_key = get_app_from_request(request)
    CaseModel = APP_CONFIG[app_key]['case_model']
    cases = CaseModel.objects.filter(
        current_level='ESC5',
        status__in=['Open', 'In Progress']
    ).order_by('-priority', '-created_at')
    return JsonResponse({
        'success': True,
        'cases': [{
            'case_id': c.case_id,
            'customer_name': c.customer_name,
            'loan_number': c.loan_number,
            'mobile': c.mobile,
            'priority': c.priority,
            'current_level': c.current_level,
            'status': c.status,
            'created_at': timezone.localtime(c.created_at).isoformat(),
            'group_name': c.group.name if c.group else None,
        } for c in cases]
    })


def get_all_cases_api(request):
    app_key = get_app_from_request(request)
    CaseModel = APP_CONFIG[app_key]['case_model']
    cases = CaseModel.objects.all().order_by('-created_at')[:50]
    return JsonResponse({
        'success': True,
        'cases': [{
            'case_id': c.case_id,
            'customer_name': c.customer_name,
            'loan_number': c.loan_number,
            'mobile': c.mobile,
            'priority': c.priority,
            'current_level': c.current_level,
            'status': c.status,
            'created_at': timezone.localtime(c.created_at).isoformat(),
            'group_name': c.group.name if c.group else None,
        } for c in cases]
    })


def get_case_detail_api(request, case_id):
    app_key = get_app_from_request(request)
    CaseModel = APP_CONFIG[app_key]['case_model']
    case = get_object_or_404(CaseModel, case_id=case_id)
    return JsonResponse({
        'success': True,
        'case': {
            'case_id': case.case_id,
            'customer_name': case.customer_name,
            'mobile': case.mobile,
            'current_level': case.current_level,
            'previous_level': case.previous_level,
            'status': case.status,
            'priority': case.priority,
            'loan_number': case.loan_number,
            'assigned_to_name': case.assigned_to_name,
            'created_by': case.created_by,
            'created_at': timezone.localtime(case.created_at).isoformat(),
            'resolved_at': timezone.localtime(case.resolved_at).isoformat() if case.resolved_at else None,
            'resolved_at_level': case.resolved_at_level,
            'resolved_by_role': case.resolved_by_role,
            'resolved_by': case.resolved_by,
            'issue_description': case.issue_description,
            'resolution_notes': case.resolution_notes,
            'reopen_count': case.reopen_count,
            'group_name': case.group.name if case.group else None,
        }
    })


@csrf_exempt
@require_http_methods(["POST"])
def close_case_api(request, case_id):
    agent = get_agent_from_user(request.user)
    if agent.role != 'ADMIN':
        return JsonResponse({'error': 'Only Admin can close cases'}, status=403)
    app_key = get_app_from_request(request)
    CaseModel = APP_CONFIG[app_key]['case_model']
    case = get_object_or_404(CaseModel, case_id=case_id)
    data = json.loads(request.body)
    case.close(agent, data.get('close_reason', ''))
    return JsonResponse({'success': True, 'message': 'Case closed successfully'})


@csrf_exempt
@require_http_methods(["POST"])
def reopen_case_api(request, case_id):
    agent = get_agent_from_user(request.user)
    app_key = get_app_from_request(request)
    cfg = APP_CONFIG[app_key]
    CaseModel = cfg['case_model']
    ContactModel = cfg['contact_model']
    channel_group = cfg['channel_group']

    case = get_object_or_404(CaseModel, case_id=case_id)
    data = json.loads(request.body)
    reopen_reason = data.get('reopen_reason', '')
    target_level = data.get('target_level', None)

    if agent.role != 'ADMIN':
        if case.status != 'Resolved':
            return JsonResponse({'error': f'Only resolved cases can be reopened. Current status: {case.status}'}, status=400)
        if not agent.can_view_case(case):
            return JsonResponse({'error': 'You do not have permission to reopen this case'}, status=403)

    case.reopen(agent, reopen_reason, target_level)

    # Update contact level
    ContactModel.objects.filter(mobile=case.mobile).update(current_level=case.current_level)

    # Send WebSocket update
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        channel_group,
        {
            "type": "contact.update",
            "contact": {
                "mobile": case.mobile,
                "current_level": case.current_level,
            }
        }
    )
    return JsonResponse({
        'success': True,
        'message': f'Case reopened to {case.current_level}',
        'case': {
            'case_id': case.case_id,
            'status': case.status,
            'current_level': case.current_level,
            'reopen_count': case.reopen_count,
            'reopened_at': timezone.localtime(case.reopened_at).isoformat() if case.reopened_at else None,
        }
    })


@csrf_exempt
@require_http_methods(["POST"])
def resolve_case_api(request, case_id):
    agent = get_agent_from_user(request.user)
    if agent.role != 'ADMIN':
        return JsonResponse({'error': 'Only Admin can resolve ESC5 cases'}, status=403)
    app_key = get_app_from_request(request)
    CaseModel = APP_CONFIG[app_key]['case_model']
    case = get_object_or_404(CaseModel, case_id=case_id)
    data = json.loads(request.body)
    case.resolve(agent, data.get('resolution_notes', ''))
    return JsonResponse({'success': True, 'message': 'Case resolved successfully'})


def get_case_timeline_api(request, case_id):
    app_key = get_app_from_request(request)
    CaseModel = APP_CONFIG[app_key]['case_model']
    case = get_object_or_404(CaseModel, case_id=case_id)
    logs = case.escalation_logs.all().order_by('-created_at')[:50]
    return JsonResponse({
        'logs': [{
            'from_level': log.from_level,
            'to_level': log.to_level,
            'escalated_by': log.escalated_by,
            'reason': log.reason,
            'created_at': log.created_at.isoformat()
        } for log in logs]
    })


@csrf_exempt
@require_http_methods(["POST"])
def edit_case_api(request, case_id):
    """Admin-only endpoint to edit case fields"""
    agent = get_agent_from_user(request.user)
    if agent.role != 'ADMIN':
        return JsonResponse({'error': 'Only Admin can edit cases'}, status=403)

    app_key = get_app_from_request(request)
    CaseModel = APP_CONFIG[app_key]['case_model']
    case = get_object_or_404(CaseModel, case_id=case_id)
    data = json.loads(request.body)

    # Allowed fields to edit
    if 'loan_number' in data:
        case.loan_number = data['loan_number']
    if 'customer_name' in data:
        case.customer_name = data['customer_name']
    if 'issue_description' in data:
        case.issue_description = data['issue_description']
    
    case.save()
    return JsonResponse({'success': True, 'message': 'Case updated'})


# ============================================
# UNIFIED FAILED MESSAGES (supports ?app=...)
# ============================================
def get_filtered_qs(model, request):
    qs = model.objects.filter(status="Failed").only(
        "mobile", "template_name", "status", "error_message", "sent_at"
    ).order_by('-sent_at')
    search = request.GET.get("search")
    if search:
        qs = qs.filter(mobile__icontains=search)
    template = request.GET.get("template")
    if template:
        qs = qs.filter(template_name=template)
    return qs


def export_csv(qs, filename):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{filename}.csv"'
    writer = csv.writer(response)
    writer.writerow(["Mobile", "Template", "Status", "Error", "Sent At"])
    for row in qs.iterator(chunk_size=2000):
        sent_at = timezone.localtime(row.sent_at).replace(tzinfo=None) if row.sent_at else ""
        writer.writerow([row.mobile, row.template_name, row.status, row.error_message, sent_at])
    return response


@login_required
def failed_messages(request, app_key):
    if app_key not in APP_CONFIG:
        raise Http404("App not found")
    LogModel = APP_CONFIG[app_key]['log_model']
    qs = get_filtered_qs(LogModel, request)
    if request.GET.get("export") == "1":
        return export_csv(qs, f"failed_logs_{app_key}")
    paginator = Paginator(qs, 50)
    page_obj = paginator.get_page(request.GET.get('page'))
    templates = LogModel.objects.values_list("template_name", flat=True).distinct()
    return render(request, 'adminpanel/failed_messages.html', {
        'page_obj': page_obj,
        'templates': templates,
        'current_app': app_key,
        'app_name': APP_CONFIG[app_key]['name'],
    })


# Legacy redirects for old URLs
@login_required
def failed_messages_legacy_sms(request):
    return redirect(f"{request.path}?app=sms")


@login_required
def failed_messages_legacy_psf(request):
    return redirect(f"{request.path}?app=psf")


# ============================================
# USER MANAGEMENT (Admin only)
# ============================================
@login_required
def user_list(request):
    agent = get_agent_from_user(request.user)
    if agent.role != 'ADMIN':
        messages.error(request, "Access denied. Admin only.")
        return redirect('agent_dashboard')
    users = User.objects.all().order_by('id')
    users_with_agents = []
    for user in users:
        try:
            user_agent = Agent.objects.get(user=user)
        except Agent.DoesNotExist:
            user_agent = None
        users_with_agents.append({'user': user, 'agent': user_agent})
    return render(request, 'adminpanel/user_list.html', {'users_with_agents': users_with_agents})


@login_required
def user_create(request):
    agent = get_agent_from_user(request.user)

    if agent.role != 'ADMIN':
        messages.error(request, "Access denied. Admin only.")
        return redirect('agent_dashboard')

    groups = SupportGroup.objects.all()

    if request.method == "POST":
        username = request.POST['username']
        password = request.POST['password']
        email = request.POST.get('email', '')
        role = request.POST.get('role', 'AGENT')
        mobile = request.POST.get('mobile', '')
        display_name = request.POST.get('name', '')

        selected_groups = request.POST.getlist('groups')  # ✅ MULTI SELECT

        if User.objects.filter(username=username).exists():
            messages.error(request, "Username already exists")
        else:
            with transaction.atomic():

                is_staff = role in ['ADMIN', 'MANAGER']

                user = User.objects.create_user(
                    username=username,
                    password=password,
                    email=email,
                    is_staff=is_staff,
                    # selected_groups=groups
                    
                )

                agent_obj = Agent.objects.create(
                    user=user,
                    agent_id=f"AGT-{user.id}",
                    name=display_name or username,
                    email=email,
                    mobile=mobile,
                    role=role,
                    # groups=selected_groups
                )

                # ✅ ASSIGN MULTIPLE GROUPS
                agent_obj.groups.set(selected_groups)

                messages.success(request, f"User '{username}' created successfully")
                return redirect('admin_user_list')

    return render(request, 'adminpanel/user_create.html', {
        'role_choices': Agent.ROLE_CHOICES,
        'groups': groups
    })

@login_required
def user_edit(request, user_id):
    agent = get_agent_from_user(request.user)

    if agent.role != 'ADMIN':
        messages.error(request, "Access denied.")
        return redirect('agent_dashboard')

    user = get_object_or_404(User, id=user_id)
    user_agent = Agent.objects.filter(user=user).first()

    groups = SupportGroup.objects.all()  # ✅ IMPORTANT

    if request.method == "POST":
        username = request.POST['username']
        email = request.POST.get('email', '')
        role = request.POST.get('role', 'AGENT')
        mobile = request.POST.get('mobile', '')
        display_name = request.POST.get('name', '')

        selected_groups = request.POST.getlist('groups')  # ✅ IMPORTANT

        # Update user
        user.username = username
        user.email = email
        user.is_staff = role in ['ADMIN', 'MANAGER']

        pwd = request.POST.get('password')
        if pwd:
            user.set_password(pwd)

        user.save()

        # Update agent
        if user_agent:
            user_agent.role = role
            user_agent.name = display_name or username
            user_agent.email = email
            user_agent.mobile = mobile
            user_agent.save()

            # ✅ UPDATE GROUPS
            user_agent.groups.set(selected_groups)

        else:
            user_agent = Agent.objects.create(
                user=user,
                agent_id=f"AGT-{user.id}",
                name=display_name or username,
                email=email,
                mobile=mobile,
                role=role,
                is_active=True
            )

            user_agent.groups.set(selected_groups)

        messages.success(request, "User updated")
        return redirect('admin_user_list')

    return render(request, 'adminpanel/user_edit.html', {
        'user': user,
        'user_agent': user_agent,
        'role_choices': Agent.ROLE_CHOICES,
        'groups': groups  # ✅ IMPORTANT
    })


@login_required
def user_delete(request, user_id):
    agent = get_agent_from_user(request.user)
    if agent.role != 'ADMIN':
        messages.error(request, "Access denied. Admin only.")
        return redirect('agent_dashboard')
    user = get_object_or_404(User, id=user_id)
    if user == request.user:
        messages.error(request, "You cannot delete your own account")
        return redirect('admin_user_list')
    user.delete()
    messages.success(request, "User deleted successfully")
    return redirect('admin_user_list')


# ============================================
# OPTIONAL: ESC3 specific endpoints (app-aware)
# ============================================
@login_required
def get_esc3_cases_api(request):
    app_key = get_app_from_request(request)
    CaseModel = APP_CONFIG[app_key]['case_model']
    cases = CaseModel.objects.filter(current_level='ESC3').order_by('-priority', '-created_at')
    return JsonResponse({
        'success': True,
        'cases': [{
            'case_id': c.case_id,
            'customer_name': c.customer_name,
            'mobile': c.mobile,
            'loan_number': c.loan_number,
            'priority': c.priority,
            'current_level': c.current_level,
            'status': c.status,
            'created_at': timezone.localtime(c.created_at).isoformat(),
        } for c in cases]
    })


@login_required
def export_esc3_cases_excel(request):
    """Export ESC3 cases to Excel – accessible to Admin and Lead roles"""
    agent = get_agent_from_user(request.user)
    if agent.role not in ['ADMIN', 'LEAD']:
        return HttpResponse("Unauthorized", status=403)

    app_key = get_app_from_request(request)
    CaseModel = APP_CONFIG[app_key]['case_model']
    cases = CaseModel.objects.filter(current_level='ESC3').order_by('-priority', '-created_at')

    try:
        import pandas as pd
    except ImportError:
        return HttpResponse("pandas not installed", status=500)

    data = []
    for c in cases:
        data.append({
            'Case ID': c.case_id,
            'Customer Name': c.customer_name or '',
            'Mobile': c.mobile,
            'Loan Number': c.loan_number or '',
            'Priority': c.priority,
            'Status': c.status,
            'Current Level': c.current_level,
            'Created At': timezone.localtime(c.created_at).strftime('%Y-%m-%d %H:%M:%S'),
        })

    df = pd.DataFrame(data)
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="ESC3_Cases_{app_key}.xlsx"'
    df.to_excel(response, index=False, sheet_name='ESC3 Cases')
    return response
