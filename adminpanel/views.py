from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User, Group
from django.contrib import messages
from django.db import transaction
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
# Import models from messaging2
from messaging2.models import Agent, Case
from django.utils import timezone

def get_role_display_name(role):
    """Get display name for role"""
    role_names = {
        'AGENT': '🟢 Normal Agent (ESC1)',
        'LEGAL': '⚖️ Legal Team (ESC2)',
        'LEAD': '⭐ Team Lead (ESC3)',
        'MANAGER': '📊 Manager (ESC4)',
        'ADMIN': '🔒 Administrator (ESC5)',
    }
    return role_names.get(role, role)
# ============================================
# HELPER FUNCTIONS
# ============================================

def get_agent_from_user(user):
    """Get or create agent profile for user"""
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
            
            # Get or create agent profile
            agent = get_agent_from_user(user)
            
            # Redirect based on role
            if agent.role == 'ADMIN':
                return redirect('admin_dashboard')
            elif agent.role == 'MANAGER':
                return redirect('manager_dashboard')
            elif agent.role == 'LEAD':
                return redirect('lead_dashboard')
            elif agent.role == 'LEGAL':
                return redirect('legal_dashboard')
            else:
                return redirect('agent_dashboard')
        else:
            messages.error(request, "Invalid login")

    return render(request, 'adminpanel/login.html')


def logout_view(request):
    logout(request)
    return redirect('admin_login')


# ============================================
# DASHBOARD VIEWS
# ============================================

@login_required
def dashboard(request):
    """Admin Dashboard with statistics"""
    
    # Check if user has agent profile and redirect non-admin users
    try:
        agent = Agent.objects.get(user=request.user)
        if agent.role != 'ADMIN':
            # Direct role-based redirect without calling get_dashboard_url
            if agent.role == 'MANAGER':
                return redirect('manager_dashboard')
            elif agent.role == 'LEAD':
                return redirect('lead_dashboard')
            elif agent.role == 'LEGAL':
                return redirect('legal_dashboard')
            else:
                return redirect('agent_dashboard')
    except Agent.DoesNotExist:
        # If no agent profile exists, create one (default to AGENT)
        agent = get_agent_from_user(request.user)
        if agent.role != 'ADMIN':
            return redirect('agent_dashboard')
    
    # Get all users for the table
    users = User.objects.all().order_by('id')
    
    # Get statistics
    stats = {
        'total_cases': Case.objects.count(),
        'open_cases': Case.objects.filter(status='Open').count(),
        'in_progress_cases': Case.objects.filter(status='In Progress').count(),
        'resolved_cases': Case.objects.filter(status='Resolved').count(),
        'closed_cases': Case.objects.filter(status='Closed').count(),
        'reopened_cases':Case.objects.filter(status='Reopened').count(),
        'esc1': Case.objects.filter(current_level='ESC1').count(),
        'esc2': Case.objects.filter(current_level='ESC2').count(),
        'esc3': Case.objects.filter(current_level='ESC3').count(),
        'esc4': Case.objects.filter(current_level='ESC4').count(),
        'esc5': Case.objects.filter(current_level='ESC5').count(),
        'total_agents': Agent.objects.filter(is_active=True).count(),
    }
    
    # Build users_with_agents list for template
    users_with_agents = []
    for user in users:
        try:
            user_agent = Agent.objects.get(user=user)
        except Agent.DoesNotExist:
            user_agent = None
        users_with_agents.append({
            'user': user,
            'agent': user_agent
        })
    
    return render(request, 'adminpanel/dashboard.html', {
        'users': users,
        'users_with_agents': users_with_agents,
        'stats': stats,
        'current_agent': get_agent_from_user(request.user)
    })

from django.db.models import Q

@login_required
def search_cases_api(request):
    """API endpoint to search cases by case_id or loan_number"""
    query = request.GET.get('q', '').strip()
    if not query:
        return JsonResponse({'success': False, 'error': 'No search query provided'})
    
    # Admin can see all cases
    cases = Case.objects.filter(
        Q(case_id__icontains=query) | Q(loan_number__icontains=query)
    ).order_by('-created_at')
    
    cases_data = []
    for case in cases:
        cases_data.append({
            'case_id': case.case_id,
            'customer_name': case.customer_name,
            'mobile': case.mobile,
            'loan_number': case.loan_number,
            'status': case.status,
            'priority': case.priority,
            'created_at': case.created_at.isoformat(),
            'current_level': case.current_level,
        })
    
    return JsonResponse({
        'success': True,
        'cases': cases_data,
        'count': len(cases_data)
    })

@login_required
def user_list(request):
    """List all users with their roles"""
    # Check if admin
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
        users_with_agents.append({
            'user': user,
            'agent': user_agent
        })
    
    return render(request, 'adminpanel/user_list.html', {
        'users_with_agents': users_with_agents
    })


@login_required
def user_create(request):
    """Create new user with role - Supports all 5 teams"""
    # Check if admin
    agent = get_agent_from_user(request.user)
    if agent.role != 'ADMIN':
        messages.error(request, "Access denied. Admin only.")
        return redirect('agent_dashboard')
    
    if request.method == "POST":
        username = request.POST['username']
        password = request.POST['password']
        email = request.POST.get('email', '')
        is_staff = request.POST.get('is_staff') == "on"
        role = request.POST.get('role', 'AGENT')  # AGENT, LEGAL, LEAD, MANAGER, ADMIN

        if User.objects.filter(username=username).exists():
            messages.error(request, "Username already exists")
        else:
            with transaction.atomic():
                # Set is_staff based on role
                if role in ['ADMIN', 'MANAGER']:
                    is_staff = True
                else:
                    is_staff = False
                
                # Create user
                user = User.objects.create_user(
                    username=username, 
                    password=password, 
                    email=email,
                    is_staff=is_staff
                )
                
                # Create agent profile with selected role
                Agent.objects.create(
                    user=user,
                    agent_id=f"AGT-{user.id}",
                    name=username,
                    email=email or f"{username}@example.com",
                    role=role,  # AGENT, LEGAL, LEAD, MANAGER, ADMIN
                    is_active=True
                )
                
                # Add to corresponding Django group
                from django.contrib.auth.models import Group
                group_map = {
                    'AGENT': 'Support Agents',
                    'LEGAL': 'Legal Team',
                    'LEAD': 'Team Leads',
                    'MANAGER': 'Managers',
                    'ADMIN': 'Administrators',
                }
                group_name = group_map.get(role, 'Support Agents')
                group, _ = Group.objects.get_or_create(name=group_name)
                user.groups.add(group)
                
                messages.success(request, f"User '{username}' created with role: {get_role_display_name(role)}")
                return redirect('admin_user_list')

    return render(request, 'adminpanel/user_create.html', {
        'role_choices': Agent.ROLE_CHOICES
    })




@login_required
def user_edit(request, user_id):
    """Edit existing user - Can change role"""
    # Check if admin
    agent = get_agent_from_user(request.user)
    if agent.role != 'ADMIN':
        messages.error(request, "Access denied. Admin only.")
        return redirect('agent_dashboard')
    
    user = get_object_or_404(User, id=user_id)
    user_agent = Agent.objects.filter(user=user).first()

    if request.method == "POST":
        username = request.POST['username']
        email = request.POST.get('email', '')
        role = request.POST.get('role', 'AGENT')
        
        # Set is_staff based on role
        is_staff = role in ['ADMIN', 'MANAGER']
        
        user.username = username
        user.email = email
        user.is_staff = is_staff

        pwd = request.POST.get('password')
        if pwd:
            user.set_password(pwd)

        user.save()
        
        # Update or create agent profile
        if user_agent:
            user_agent.role = role
            user_agent.name = username
            user_agent.email = email
            user_agent.save()
        else:
            Agent.objects.create(
                user=user,
                agent_id=f"AGT-{user.id}",
                name=username,
                email=email or f"{username}@example.com",
                role=role,
                is_active=True
            )
        
        # Update group membership
        from django.contrib.auth.models import Group
        group_map = {
            'AGENT': 'Support Agents',
            'LEGAL': 'Legal Team',
            'LEAD': 'Team Leads',
            'MANAGER': 'Managers',
            'ADMIN': 'Administrators',
        }
        group_name = group_map.get(role, 'Support Agents')
        group, _ = Group.objects.get_or_create(name=group_name)
        user.groups.clear()
        user.groups.add(group)
        
        messages.success(request, f"User '{username}' updated with role: {get_role_display_name(role)}")
        return redirect('admin_user_list')

    return render(request, 'adminpanel/user_edit.html', {
        'user': user,
        'user_agent': user_agent,
        'role_choices': Agent.ROLE_CHOICES
    })


@login_required
def user_delete(request, user_id):
    """Delete user"""
    # Check if admin
    agent = get_agent_from_user(request.user)
    if agent.role != 'ADMIN':
        messages.error(request, "Access denied. Admin only.")
        return redirect('agent_dashboard')
    
    user = get_object_or_404(User, id=user_id)
    
    # Don't allow deleting yourself
    if user == request.user:
        messages.error(request, "You cannot delete your own account")
        return redirect('admin_user_list')
    
    user.delete()
    messages.success(request, "User deleted successfully")
    return redirect('admin_user_list')





from django.core.paginator import Paginator
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.http import HttpResponse
from django.utils.timezone import localtime
import csv


# ✅ COMMON QUERY FUNCTION (FAST FILTER)
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


# ✅ FAST CSV EXPORT (NO MEMORY ISSUE)
def export_csv(qs, filename):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{filename}.csv"'

    writer = csv.writer(response)
    writer.writerow(["Mobile", "Template", "Status", "Error", "Sent At"])

    for row in qs.iterator(chunk_size=2000):  # 🔥 VERY FAST
        sent_at = localtime(row.sent_at).replace(tzinfo=None) if row.sent_at else ""

        writer.writerow([
            row.mobile,
            row.template_name,
            row.status,
            row.error_message,
            sent_at
        ])

    return response


# ===========================
# 🔹 VIEW 1
# ===========================
from messaging.models import SmsWhatsAppLog

@login_required
def failed_messages(request):
    qs = get_filtered_qs(SmsWhatsAppLog, request)

    # 🚀 EXPORT
    if request.GET.get("export") == "1":
        return export_csv(qs, "failed_logs")

    # 📄 PAGINATION
    paginator = Paginator(qs, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    templates = SmsWhatsAppLog.objects.values_list(
        "template_name", flat=True
    ).distinct()

    return render(request, 'adminpanel/failed_messages.html', {
        'page_obj': page_obj,
        'templates': templates
    })


# ===========================
# 🔹 VIEW 2
# ===========================
from messaging2.models import SmsWhatsAppLog2
from django.http import JsonResponse,HttpResponse, Http404, StreamingHttpResponse
from datetime import datetime, timedelta
from django.utils import timezone



@login_required
def failed_messages2(request):
    qs = get_filtered_qs(SmsWhatsAppLog2, request)

    # 🚀 EXPORT
    if request.GET.get("export") == "1":
        return export_csv(qs, "failed_logs2")

    # 📄 PAGINATION
    paginator = Paginator(qs, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    templates = SmsWhatsAppLog2.objects.values_list(
        "template_name", flat=True
    ).distinct()

    return render(request, 'adminpanel/failed_messages2.html', {
        'page_obj': page_obj,
        'templates': templates
    })

# Add these to your views.py

def get_level_distribution_api(request):
    """Get case count by escalation level"""
    try:
        data = {
            'esc1': Case.objects.filter(current_level='ESC1').count(),
            'esc2': Case.objects.filter(current_level='ESC2').count(),
            'esc3': Case.objects.filter(current_level='ESC3').count(),
            'esc4': Case.objects.filter(current_level='ESC4').count(),
            'esc5': Case.objects.filter(current_level='ESC5').count(),
            'resolved': Case.objects.filter(current_level='RESOLVED').count(),
            'closed': Case.objects.filter(current_level='CLOSED').count(),
        }
        return JsonResponse(data)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def get_weekly_trend_api(request):
    """Get weekly case trend for charts"""
    try:
        labels = []
        new_cases = []
        resolved = []
        
        for i in range(6, -1, -1):
            date = timezone.now().date() - timedelta(days=i)
            labels.append(date.strftime('%a, %b %d'))
            
            start_of_day = timezone.make_aware(datetime.combine(date, datetime.min.time()))
            end_of_day = start_of_day + timedelta(days=1)
            
            new_cases.append(Case.objects.filter(
                created_at__gte=start_of_day, created_at__lt=end_of_day
            ).count())
            
            resolved.append(Case.objects.filter(
                resolved_at__gte=start_of_day, resolved_at__lt=end_of_day
            ).count())
        
        return JsonResponse({
            'labels': labels,
            'new_cases': new_cases,
            'resolved': resolved
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def get_open_cases_api(request):
    """Get all open cases"""
    try:
        cases = Case.objects.filter(status__in=['Open', 'In Progress']).order_by('-priority', '-created_at')[:50]
        return JsonResponse({
            'success': True,
            'cases': [{
                'case_id': c.case_id,
                'customer_name': c.customer_name,
                'loan_number':c.loan_number,
                'mobile': c.mobile,
                'priority': c.priority,
                'current_level': c.current_level,
                'created_at': timezone.localtime(c.created_at).isoformat(),
            } for c in cases]
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def get_closed_cases_api(request):
    """Get all closed cases"""
    try:
        cases = Case.objects.filter(status='Closed').order_by('-closed_at')[:50]
        return JsonResponse({
            'success': True,
            'cases': [{
                'case_id': c.case_id,
                'customer_name': c.customer_name,
                'mobile': c.mobile,
                'loan_number':c.loan_number,
                'priority': c.priority,
                'current_level': c.current_level,
                'created_at': timezone.localtime(c.created_at).isoformat(),
            } for c in cases]
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def get_esc5_cases_api(request):
    """Get all ESC5 cases awaiting admin review"""
    try:
        cases = Case.objects.filter(
            current_level='ESC5', 
            status__in=['Open', 'In Progress']   # ← add 'In Progress'
        ).order_by('-priority', '-created_at')
        return JsonResponse({
            'success': True,
            'cases': [{
                'case_id': c.case_id,
                'customer_name': c.customer_name,
                'mobile': c.mobile,
                'loan_number':c.loan_number,
                'priority': c.priority,
                'current_level': c.current_level,
                'created_at': timezone.localtime(c.created_at).isoformat(),
            } for c in cases]
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def get_all_cases_api(request):
    """Get all cases (admin view)"""
    try:
        cases = Case.objects.all().order_by('-created_at')[:50]
        return JsonResponse({
            'success': True,
            'cases': [{
                'case_id': c.case_id,
                'customer_name': c.customer_name,
                'mobile': c.mobile,
                'loan_number':c.loan_number,
                'priority': c.priority,
                'current_level': c.current_level,
                'status': c.status,
                'created_at': timezone.localtime(c.created_at).isoformat(),
            } for c in cases]
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
    
# Add these imports at the top
import json
from datetime import datetime, timedelta
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse
from django.utils import timezone

# ============================================
# CASE API ENDPOINTS (Add these)
# ============================================

def get_case_detail_api(request, case_id):
    """Get case details for modal"""
    try:
        case = get_object_or_404(Case, case_id=case_id)
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
                'loan_number':case.loan_number,
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
            }
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def close_case_api(request, case_id):
    """Close a case - Admin only"""
    try:
        agent = get_agent_from_user(request.user)
        if agent.role != 'ADMIN':
            return JsonResponse({'error': 'Only Admin can close cases'}, status=403)
        
        case = get_object_or_404(Case, case_id=case_id)
        data = json.loads(request.body)
        
        case.close(agent, data.get('close_reason', ''))
        return JsonResponse({'success': True, 'message': 'Case closed successfully'})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def reopen_case_api(request, case_id):
    """Reopen a case - Admin can reopen any case"""
    try:
        agent = get_agent_from_user(request.user)
        case = get_object_or_404(Case, case_id=case_id)
        data = json.loads(request.body)
        
        reopen_reason = data.get('reopen_reason', '')
        target_level = data.get('target_level', None)
        
        # Admin can reopen any case (including closed)
        if agent.role != 'ADMIN':
            # Non-admin can only reopen resolved cases at their level
            if case.status != 'Resolved':
                return JsonResponse({
                    'error': f'Only resolved cases can be reopened. Current status: {case.status}'
                }, status=400)
            if not agent.can_view_case(case):
                return JsonResponse({
                    'error': 'You do not have permission to reopen this case'
                }, status=403)
        
        # Reopen the case
        case.reopen(agent, reopen_reason, target_level)
        
        # Update contact level
        from messaging2.models import ChatContact2
        ChatContact2.objects.filter(mobile=case.mobile).update(
            current_level=case.current_level
        )
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            "global_contacts2",
                {
                    "type": "contact.update",
                    "contact": {
                        "mobile": case.mobile,
                        "current_level": 'CLOSED'
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
                'reopened_at': timezone.localtime(case.reopened_at).isoformat() if case.reopened_at else None,            }
        })
        
    except Case.DoesNotExist:
        return JsonResponse({'error': 'Case not found'}, status=404)
    except PermissionError as e:
        return JsonResponse({'error': str(e)}, status=403)
    except ValueError as e:
        return JsonResponse({'error': str(e)}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
    

@csrf_exempt
@require_http_methods(["POST"])
def resolve_case_api(request, case_id):
    """Resolve a case (for ESC5 cases)"""
    try:
        agent = get_agent_from_user(request.user)
        if agent.role != 'ADMIN':
            return JsonResponse({'error': 'Only Admin can resolve ESC5 cases'}, status=403)
        
        case = get_object_or_404(Case, case_id=case_id)
        data = json.loads(request.body)
        
        case.resolve(agent, data.get('resolution_notes', ''))
        return JsonResponse({'success': True, 'message': 'Case resolved successfully'})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def get_case_timeline_api(request, case_id):
    """Get case escalation timeline"""
    try:
        case = get_object_or_404(Case, case_id=case_id)
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
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)