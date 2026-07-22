
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
from django.conf import settings
from messaging.models import CaseDescriptionLog as SmsCaseDescriptionLog
from messaging2.models import CaseDescriptionLog as PsfCaseDescriptionLog
from special_cases.models import CaseDescriptionLog as SplCaseDescriptionLog

# ============================================
# APP CONFIGURATION
# ============================================
from messaging2.utils import get_template_text_from_whatsapp2
from messaging.utils import get_template_text_from_whatsapp
from .utils import render_template_text
from messaging2.utils import upload_whatsapp_media2,build_payload2,open_legal_pdf2,format_mobile2
from messaging.utils import upload_whatsapp_media,build_payload,open_legal_pdf,format_mobile

# ============================================
# APP CONFIGURATION
# ============================================
APP_CONFIG = {
    'psf': {
        'name': 'PSF',
        'app_name':'Padma Sai Holdings Private Limited',
        'case_model': psfCase,
        'log_model': SmsWhatsAppLog2,
        'contact_model': ChatContact2,
        'channel_group': 'global_contacts2',
        'chat_prefix': 'chat2', 
        'description_log_model': PsfCaseDescriptionLog,
        'upload_media_func': upload_whatsapp_media2,   # PSF's upload function
         'build_payload_func': build_payload2, 
         'format_mobile_func': format_mobile2,
         'open_legal_pdf_func': open_legal_pdf2,
        'templates': {
            'open': 'ticket_open',    # Replace with actual template name for PSF
            'close': 'ticket_closed',
            'welcome':'welcome_message',
            'payment':'pay_now_link',
          
            'ptp': {
        'en': 'ptp_confirm_en',
        'te': 'ptp_confirm_te'
    }
        },
        'get_template_text': get_template_text_from_whatsapp2,
        'render_template_text': render_template_text,
        'whatsapp': {
            'phone_number_id': settings.WHATSAPP2_PHONE_NUMBER_ID,   # Use PSF's
            'access_token': settings.WHATSAPP2_ACCESS_TOKEN,
        },
    },
    'sms': {
        'name': 'SMS',
        'app_name':'SM SQUARE CREDIT SERVICES PRIVATE LIMITED',
        'case_model': smsCase,
        'log_model': SmsWhatsAppLog,
        'contact_model': ChatContact,
        'channel_group': 'global_contacts',
        'chat_prefix': 'chat', 
        'description_log_model': SmsCaseDescriptionLog,
        'get_template_text': get_template_text_from_whatsapp,
        'render_template_text': render_template_text,
        'upload_media_func': upload_whatsapp_media2,   # PSF's upload function
        'build_payload_func': build_payload2, 
        'format_mobile_func': format_mobile2,
        'open_legal_pdf_func': open_legal_pdf2,
        'templates': {
            'open': 'ticket_open',    # Replace with actual template name for PSF
            'close': 'ticket_closed',
            'welcome':'welcome_message',
            'payment':'pay_now_link',
            'ptp': {
        'en': 'ptp_confirm_en',
        'te': 'ptp_confirm_te'
    }
        },
        'whatsapp': {
            'phone_number_id': settings.
WHATSAPP_PHONE_NUMBER_ID,   # Use PSF's
            'access_token': settings.WHATSAPP_ACCESS_TOKEN,
        },
    },



    'spl': {
        'name': 'SPL Cases',
        'app_name':'Padma Sai Holdings Private Limited',

        'case_model': SplCase,
        'log_model': SmsWhatsAppLog3,
        'contact_model': ChatContact3,
        'channel_group': 'global_contacts3',
        'chat_prefix': 'chat3', 
        'description_log_model': SplCaseDescriptionLog,
        'get_template_text': get_template_text_from_whatsapp,
        'render_template_text': render_template_text,
        'templates': {
            'open': 'ticket_opened',    # Replace with actual template name for PSF
            'close': 'ticket_closed',
            'welcome':'welcome_message',
        },
        'whatsapp': {
            'phone_number_id': settings.WHATSAPP3_PHONE_NUMBER_ID,   # Use PSF's
            'access_token': settings.WHATSAPP3_ACCESS_TOKEN,
        },
    },
}
# ============================================
# HELPER FUNCTIONS
# ============================================

def get_models_for_app(request):
    app_key = get_app_from_request(request)
    cfg = APP_CONFIG[app_key]
    return cfg['case_model'], cfg['contact_model'], cfg['log_model'], cfg['channel_group']

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


from adminpanel.models import SupportGroup, Subgroup  # ensure this import exists
from messaging2.tasks import send_ticket_open_message
@csrf_exempt
def create_case_from_chat_api2(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        data = json.loads(request.body)
        mobile = data.get('mobile', '')

        # Get app‑aware models (case, contact, log)
        CaseModel, ContactModel, LogModel, _ = get_models_for_app(request)

        # ✅ Dynamic log check – uses correct app's log table
        if not LogModel.objects.filter(mobile=mobile).exists():
            app_key = request.GET.get('app', 'psf')
            return JsonResponse({
                'error': f'This number has no WhatsApp messages in the {app_key} app. Cannot create case here.'
            }, status=400)

        customer_name = data.get('customer_name') or mobile
        agent_name = data.get('agent_name', 'Agent')
        issue_description = data.get('issue_description', '')
        loan_number = data.get('loan_number', '')
        vehicle_number = data.get('vehicle_no', '')   # optional
        group_name = data.get('group', 'Collections')
        subgroup_id = data.get('subgroup_id', None)   # NEW
        escalate_to = data.get('escalate_to', None)
        force_new = data.get('force_new', False)

        group_obj = SupportGroup.objects.filter(name=group_name).first()
        if not group_obj:
            return JsonResponse({'error': 'Invalid group'}, status=400)

        # ─── Handle subgroup ────────────────────────────────────────────
        subgroup_obj = None
        if subgroup_id:
            try:
                subgroup_obj = Subgroup.objects.get(id=subgroup_id)
                # Validate that subgroup belongs to the selected group
                if subgroup_obj.group != group_obj:
                    return JsonResponse({'error': 'Subgroup does not belong to the selected group'}, status=400)
            except Subgroup.DoesNotExist:
                return JsonResponse({'error': 'Invalid subgroup ID'}, status=400)

        # ─── Check existing active case ────────────────────────────────
        if not force_new:
            existing_case = CaseModel.objects.filter(
                mobile=mobile,
                status__in=['Open', 'In Progress', 'Resolved']
            ).first()
            if existing_case:
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

        initial_level = 'ESC1'
        if escalate_to and escalate_to.startswith('ESC') and escalate_to != 'ESC1':
            initial_level = escalate_to

        case_id = f"CASE-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
        case = CaseModel.objects.create(
            case_id=case_id,
            customer_name=customer_name,
            mobile=mobile,
            loan_number=loan_number,
            vehicle_number=vehicle_number,   # added
            issue_description=issue_description[:500],
            source='WhatsApp',
            current_level=initial_level,
            status='Open',
            priority='Medium',
            created_by=agent_name,
            group=group_obj,
            subgroup=subgroup_obj,           # NEW
            assigned_to=None,
            assigned_to_name=None,
        )

        # ─── Assignment & Escalation Logic ────────────────────────────
        if initial_level == 'ESC1':
            auto_assign(case)
            if case.assigned_to:
                case.assigned_to_name = case.assigned_to.name
                case.save(update_fields=['assigned_to_name'])
        else:
            case.escalation_logs.create(
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
        send_ticket_open_message.delay(app_key, case.id)

        return JsonResponse({
            'success': True,
            'case': {
                'case_id': case.case_id,
                'customer_name': case.customer_name,
                'loan_number': case.loan_number,
                'vehicle_number': case.vehicle_number,   # optional
                'assigned_to_name': case.assigned_to_name or 'Unassigned',
                'current_level': case.current_level,
                'status': case.status,
                'subgroup_name': case.subgroup.name if case.subgroup else None,   # NEW
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
        if user is not None:
            try:
                agent = user.agent_profile  # related_name from Agent
                if not agent.can_login:
                    messages.error(request, "Your account is disabled. Please contact admin.")
                    return render(request, 'adminpanel/login.html')
            except Agent.DoesNotExist:
                messages.error(request, "Agent profile not found.")
                return render(request, 'adminpanel/login.html')
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


# views.py
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.urls import reverse

def logout_view(request):
    logout(request)
    # Redirect to your login page with a timeout flag
    return redirect(reverse('admin_login') + '?timeout=1')

from django.contrib.admin.views.decorators import staff_member_required

@staff_member_required  # only admins/staff can toggle
def toggle_can_login(request, user_id):
    agent = get_object_or_404(Agent, user_id=user_id)
    agent.can_login = not agent.can_login
    agent.save(update_fields=['can_login'])
    status = "enabled" if agent.can_login else "disabled"
    messages.success(request, f"Login access {status} for {agent.user.username}.")
    return redirect('admin_user_list')  # name of your user list URL

import random
from datetime import timedelta
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import authenticate, login as auth_login
from django.contrib.auth.models import User
from django.utils.timezone import now
from django.contrib.auth.decorators import login_required

# Import forms
from .forms import ForgotPasswordForm, OTPVerificationForm, ResetPasswordForm

# Import the WhatsApp utility
from .utils import send_whatsapp_otp

# OTP expiry time (in minutes)
OTP_EXPIRY_MINUTES = 5




# ------------------- STEP 1: FORGOT PASSWORD -------------------
def forgot_password(request):
    """
    Step 1: User enters username/email -> Send OTP via WhatsApp
    """
    if request.user.is_authenticated:
        return redirect('agent_dashboard')

    if request.method == 'POST':
        form = ForgotPasswordForm(request.POST)
        if form.is_valid():
            user = form.cleaned_data['user']
            otp = str(random.randint(100000, 999999))
            
            request.session['reset_user_id'] = user.id
            request.session['reset_otp'] = otp
            request.session['reset_otp_time'] = now().isoformat()

            try:
                agent = user.agent_profile
                phone = agent.mobile
                if not phone:
                    messages.error(request, "No mobile number registered.")
                    return render(request, 'adminpanel/forgot_password.html', {'form': form})
                
                # Format phone number for Meta
                if phone.startswith('+'):
                    phone = phone[1:]
                if not phone.startswith('91'):   # India country code
                    phone = '91' + phone
                
                send_whatsapp_otp(phone, otp)
                messages.success(request, f"OTP sent to WhatsApp ({phone[-4:]})")
                return redirect('verify_otp')
                
            except User.agent_profile.RelatedObjectDoesNotExist:
                messages.error(request, "Agent profile not found.")
                return render(request, 'adminpanel/forgot_password.html', {'form': form})
            except Exception as e:
                messages.error(request, f"Failed to send OTP: {e}")
                return render(request, 'adminpanel/forgot_password.html', {'form': form})
    else:
        form = ForgotPasswordForm()
    
    return render(request, 'adminpanel/forgot_password.html', {'form': form})

# ------------------- STEP 2: VERIFY OTP -------------------
def verify_otp(request):
    """
    Step 2: User enters the OTP received on WhatsApp
    """
    # Check if session has required data
    if 'reset_user_id' not in request.session or 'reset_otp' not in request.session:
        messages.error(request, "Session expired. Please start over.")
        return redirect('forgot_password')

    if request.method == 'POST':
        form = OTPVerificationForm(request.POST)
        if form.is_valid():
            entered_otp = form.cleaned_data['otp']
            stored_otp = request.session.get('reset_otp')
            otp_time_str = request.session.get('reset_otp_time')
            
            if not stored_otp or not otp_time_str:
                messages.error(request, "Session expired. Please request a new OTP.")
                return redirect('forgot_password')

            # Check if OTP has expired
            otp_time = datetime.fromisoformat(otp_time_str)
            if now() > otp_time + timedelta(minutes=OTP_EXPIRY_MINUTES):
                # Clear the OTP from session
                request.session.pop('reset_otp', None)
                request.session.pop('reset_otp_time', None)
                messages.error(request, f"OTP has expired. Please request a new one.")
                return redirect('forgot_password')

            # Verify OTP
            if entered_otp == stored_otp:
                # Mark as verified and clear OTP fields
                request.session['reset_verified'] = True
                request.session.pop('reset_otp', None)
                request.session.pop('reset_otp_time', None)
                messages.success(request, "OTP verified! Now set your new password.")
                return redirect('reset_password')
            else:
                messages.error(request, "Invalid OTP. Please try again.")
    else:
        form = OTPVerificationForm()
    
    return render(request, 'adminpanel/verify_otp.html', {'form': form})

def reset_password(request):
    """
    Step 3: Set new password after OTP verification
    """
    # Ensure user has verified OTP
    if not request.session.get('reset_verified'):
        messages.error(request, "You must verify your OTP first.")
        return redirect('forgot_password')

    user_id = request.session.get('reset_user_id')
    if not user_id:
        messages.error(request, "Session expired. Please start over.")
        return redirect('forgot_password')

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        messages.error(request, "User not found.")
        return redirect('forgot_password')

    if request.method == 'POST':
        form = ResetPasswordForm(request.POST)
        if form.is_valid():
            new_password = form.cleaned_data['new_password']
            
            # Set the new password
            user.set_password(new_password)
            user.save()
            
            # Clear the entire session to log out any pending state
            request.session.flush()
            
            messages.success(request, "✅ Password reset successfully! Please login with your new password.")
            return redirect('admin_login')
    else:
        form = ResetPasswordForm()
    
    return render(request, 'adminpanel/reset_password.html', {'form': form})


# views.py
@login_required
def create_group(request):
    agent = get_agent_from_user(request.user)

    if agent.role != 'ADMIN':
        messages.error(request, "Access denied")
        return redirect('agent_dashboard')

    if request.method == "POST":
        name = request.POST.get('name').strip()
        if not name:
            messages.error(request, "Group name is required")
            return redirect('manage_groups')

        if SupportGroup.objects.filter(name__iexact=name).exists():
            messages.error(request, f"Group '{name}' already exists")
        else:
            SupportGroup.objects.create(name=name)
            messages.success(request, f"Group '{name}' created successfully")
        return redirect('manage_groups')

    return render(request, 'adminpanel/create_group.html')


@login_required
def create_subgroup(request):
    agent = get_agent_from_user(request.user)

    if agent.role != 'ADMIN':
        messages.error(request, "Access denied")
        return redirect('agent_dashboard')

    groups = SupportGroup.objects.all().order_by('name')

    if request.method == "POST":
        name = request.POST.get('name', '').strip()
        group_id = request.POST.get('group')

        if not name:
            messages.error(request, "Subgroup name is required")
            return redirect('manage_groups')

        if not group_id:
            messages.error(request, "Please select a parent group")
            return redirect('manage_groups')

        try:
            parent_group = SupportGroup.objects.get(id=group_id)
        except SupportGroup.DoesNotExist:
            messages.error(request, "Selected group does not exist")
            return redirect('manage_groups')

        if Subgroup.objects.filter(name__iexact=name, group=parent_group).exists():
            messages.error(request, f"A subgroup named '{name}' already exists under group '{parent_group.name}'")
        else:
            Subgroup.objects.create(name=name, group=parent_group)
            messages.success(request, f"Subgroup '{name}' created under group '{parent_group.name}'")

        return redirect('manage_groups')

    return render(request, 'adminpanel/create_subgroup.html', {'groups': groups})


@login_required
def create_category(request):
    agent = get_agent_from_user(request.user)
    if agent.role != 'ADMIN':
        messages.error(request, "Access denied")
        return redirect('agent_dashboard')

    groups = SupportGroup.objects.all().order_by('name')

    if request.method == "POST":
        name = request.POST.get('name', '').strip()
        group_id = request.POST.get('group')

        if not name:
            messages.error(request, "Category name is required")
            return redirect('create_category')

        if not group_id:
            messages.error(request, "Please select a department (group)")
            return redirect('create_category')

        try:
            parent_group = SupportGroup.objects.get(id=group_id)
        except SupportGroup.DoesNotExist:
            messages.error(request, "Selected group does not exist")
            return redirect('create_category')

        # Check duplicate Category under same group (case-insensitive)
        if Category.objects.filter(name__iexact=name, group=parent_group).exists():
            messages.error(request, f"A category named '{name}' already exists under group '{parent_group.name}'")
        else:
            Category.objects.create(name=name, group=parent_group)
            messages.success(request, f"Category '{name}' created under group '{parent_group.name}'")

        return redirect('create_category')

    return render(request, 'adminpanel/create_category.html', {'groups': groups})




@login_required
def manage_categories(request):
    agent = get_agent_from_user(request.user)
    if agent.role != 'ADMIN':
        messages.error(request, "Access denied")
        return redirect('agent_dashboard')

    groups = SupportGroup.objects.all().order_by('name')
    filter_group = request.GET.get('group')
    categories = Category.objects.select_related('group').all().order_by('name')
    if filter_group:
        categories = categories.filter(group_id=filter_group)

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'create':
            name = request.POST.get('name', '').strip()
            group_id = request.POST.get('group')
            if not name or not group_id:
                messages.error(request, "Name and department are required")
            else:
                try:
                    group = SupportGroup.objects.get(id=group_id)
                    if Category.objects.filter(name__iexact=name, group=group).exists():
                        messages.error(request, f"Category '{name}' already exists under '{group.name}'")
                    else:
                        Category.objects.create(name=name, group=group)
                        messages.success(request, f"Category '{name}' created")
                except SupportGroup.DoesNotExist:
                    messages.error(request, "Invalid department selected")
            return redirect('manage_categories')

        elif action == 'edit':
            cat_id = request.POST.get('category_id')
            name = request.POST.get('name', '').strip()
            group_id = request.POST.get('group')
            try:
                category = Category.objects.get(id=cat_id)
                if not name or not group_id:
                    messages.error(request, "Name and department are required")
                else:
                    try:
                        group = SupportGroup.objects.get(id=group_id)
                        # Check duplicate except itself
                        if Category.objects.filter(name__iexact=name, group=group).exclude(id=cat_id).exists():
                            messages.error(request, f"Another category named '{name}' already exists under '{group.name}'")
                        else:
                            category.name = name
                            category.group = group
                            category.save()
                            messages.success(request, "Category updated")
                    except SupportGroup.DoesNotExist:
                        messages.error(request, "Invalid department selected")
            except Category.DoesNotExist:
                messages.error(request, "Category not found")
            return redirect('manage_categories')

        elif action == 'delete':
            cat_id = request.POST.get('category_id')
            try:
                category = Category.objects.get(id=cat_id)
                category.delete()
                messages.success(request, "Category deleted")
            except Category.DoesNotExist:
                messages.error(request, "Category not found")
            return redirect('manage_categories')

    context = {
        'categories': categories,
        'groups': groups,
        'filter_group': filter_group,
    }
    return render(request, 'adminpanel/manage_category.html', context)


@login_required
def manage_groups_subgroups(request):
    agent = get_agent_from_user(request.user)
    if agent.role != 'ADMIN':
        messages.error(request, "Access denied")
        return redirect('agent_dashboard')

    all_groups = SupportGroup.objects.prefetch_related('subgroup_set').order_by('name')
    return render(request, 'adminpanel/manage_group.html', {
        'groups': all_groups,
        'current_agent': agent,
    })


@login_required
def edit_group(request, group_id):
    agent = get_agent_from_user(request.user)
    if agent.role != 'ADMIN':
        messages.error(request, "Access denied")
        return redirect('manage_groups')

    group = get_object_or_404(SupportGroup, id=group_id)

    if request.method == "POST":
        new_name = request.POST.get('name', '').strip()
        if not new_name:
            messages.error(request, "Group name is required")
            return redirect('manage_groups')

        # Check duplicate (case-insensitive, exclude current)
        if SupportGroup.objects.filter(name__iexact=new_name).exclude(id=group.id).exists():
            messages.error(request, f"A group named '{new_name}' already exists")
        else:
            group.name = new_name
            group.save()
            messages.success(request, f"Group updated to '{new_name}'")
        return redirect('manage_groups')

    # GET: return modal content or rendered form (we'll handle via modal)
    return render(request, 'adminpanel/edit_group_modal.html', {'group': group})


@login_required
def delete_group(request, group_id):
    agent = get_agent_from_user(request.user)
    if agent.role != 'ADMIN':
        messages.error(request, "Access denied")
        return redirect('manage_groups')

    group = get_object_or_404(SupportGroup, id=group_id)
    if group.subgroup_set.exists():
        messages.error(request, f"Cannot delete group '{group.name}' because it has subgroups. Delete subgroups first.")
    else:
        group_name = group.name
        group.delete()
        messages.success(request, f"Group '{group_name}' deleted successfully")
    return redirect('manage_groups')


@login_required
def edit_subgroup(request, subgroup_id):
    agent = get_agent_from_user(request.user)
    if agent.role != 'ADMIN':
        messages.error(request, "Access denied")
        return redirect('manage_groups')

    subgroup = get_object_or_404(Subgroup, id=subgroup_id)
    groups = SupportGroup.objects.all().order_by('name')

    if request.method == "POST":
        new_name = request.POST.get('name', '').strip()
        new_group_id = request.POST.get('group')
        if not new_name:
            messages.error(request, "Subgroup name is required")
            return redirect('manage_groups')
        if not new_group_id:
            messages.error(request, "Parent group is required")
            return redirect('manage_groups')

        try:
            parent_group = SupportGroup.objects.get(id=new_group_id)
        except SupportGroup.DoesNotExist:
            messages.error(request, "Selected group does not exist")
            return redirect('manage_groups')

        # Check duplicate within the same group (exclude current)
        if Subgroup.objects.filter(name__iexact=new_name, group=parent_group).exclude(id=subgroup.id).exists():
            messages.error(request, f"A subgroup named '{new_name}' already exists under group '{parent_group.name}'")
        else:
            subgroup.name = new_name
            subgroup.group = parent_group
            subgroup.save()
            messages.success(request, f"Subgroup updated to '{new_name}' under '{parent_group.name}'")
        return redirect('manage_groups')

    return render(request, 'adminpanel/edit_subgroup_modal.html', {'subgroup': subgroup, 'groups': groups})


@login_required
def delete_subgroup(request, subgroup_id):
    agent = get_agent_from_user(request.user)
    if agent.role != 'ADMIN':
        messages.error(request, "Access denied")
        return redirect('manage_groups')

    subgroup = get_object_or_404(Subgroup, id=subgroup_id)
    subgroup_name = subgroup.name
    group_name = subgroup.group.name
    subgroup.delete()
    messages.success(request, f"Subgroup '{subgroup_name}' (under '{group_name}') deleted successfully")
    return redirect('manage_groups')


# ============================================
# UNIFIED ADMIN DASHBOARD (supports ?app=...)
@login_required
def dashboard(request):
    agent = get_agent_from_user(request.user)
    if agent.role != 'ADMIN':
        if agent.role == 'MANAGER':
            return redirect('manager_dashboard')
        elif agent.role == 'HEAD':
            return redirect('head_dashboard')
        elif agent.role == 'EXECUTIVE':
            return redirect('executive_dashboard')
        else:
            return redirect('agent_dashboard')

    app_key = get_app_from_request(request)
    cfg = APP_CONFIG[app_key]
    CaseModel = cfg['case_model']

    # ─── Base queryset ──────────────────────────────────────────
    all_cases = CaseModel.objects.select_related('category')  # for categories

    # ─── Stats ──────────────────────────────────────────────────
    stats = {
        'total_cases': all_cases.count(),
        'active_cases': all_cases.exclude(status__in=['Resolved', 'Closed']).count(),
        'open_cases': all_cases.filter(status='Open').count(),
        'in_progress_cases': all_cases.filter(status='In Progress').count(),
        'resolved_cases': all_cases.filter(status='Resolved').count(),
        'closed_cases': all_cases.filter(status='Closed').count(),
        'reopened_cases': all_cases.filter(status='Reopened').count(),
        'esc1': all_cases.filter(current_level='ESC1').count(),
        'esc2': all_cases.filter(current_level='ESC2').count(),
        'esc3': all_cases.filter(current_level='ESC3').count(),
        'esc4': all_cases.filter(current_level='ESC4').count(),
        'esc5': all_cases.filter(current_level='ESC5').count(),
        'total_agents': Agent.objects.filter(is_active=True).count(),
    }

    # ─── Category wise counts ──────────────────────────────────
    category_stats = []
    categories = Category.objects.all().order_by('name')
    for cat in categories:
        count = all_cases.filter(category=cat).count()
        if count > 0:
            category_stats.append({
                'name': cat.name,
                'count': count,
            })

    # ─── Users & Agents ──────────────────────────────────────────
    users = User.objects.all().order_by('id')
    users_with_agents = []
    for user in users:
        try:
            user_agent = Agent.objects.get(user=user)
        except Agent.DoesNotExist:
            user_agent = None
        users_with_agents.append({'user': user, 'agent': user_agent})

    all_groups = SupportGroup.objects.all().order_by('name')
    all_subgroups_qs = Subgroup.objects.select_related('group').order_by('group__name', 'name')
    all_subgroups_json = json.dumps([
        {
            'id': s.id,
            'name': s.name,
            'group_name': s.group.name,
            'group_id': s.group.id,
        }
        for s in all_subgroups_qs
    ])
    all_categories_qs = Category.objects.select_related('group').order_by('group__name', 'name')
    all_categories_json = json.dumps([
    {
        'id': c.id,
        'name': c.name,
        'group_id': c.group_id,
    }
    for c in all_categories_qs
])
    context = {
        'users': users,
        'users_with_agents': users_with_agents,
        'stats': stats,
        'category_stats': category_stats,          # NEW
        'current_agent': agent,
        'current_app': app_key,
        'app_name': cfg['name'],
        'app_list': [(key, cfg['name']) for key, cfg in APP_CONFIG.items()],
        'all_groups': all_groups,
        'all_subgroups_queryset': all_subgroups_qs,
        'all_subgroups_json': all_subgroups_json,
        'all_categories_json': all_categories_json

    }
    return render(request, 'adminpanel/dashboard.html', context)



# ============================================
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
        'active_cases': CaseModel.objects.exclude(status__in=['Resolved', 'Closed']).count(),
        'open_cases': CaseModel.objects.filter(status='Open').count(),
        'in_progress_cases': CaseModel.objects.filter(status='In Progress').count(),
        'resolved_cases': CaseModel.objects.filter(status='Resolved').count(),
        'closed_cases': CaseModel.objects.filter(status='Closed').count(),
        'reopened_cases': CaseModel.objects.filter(status='Reopened').count(),
        'total_agents': Agent.objects.filter(is_active=True).count(),
    })

# NEW: Department-wise case counts

@login_required
def get_department_stats_api(request):
    app_key = get_app_from_request(request)
    CaseModel = APP_CONFIG[app_key]['case_model']
    groups = SupportGroup.objects.all()
    dept_stats = []

    # Count only cases that have a department AND are active (exclude Resolved/Closed)
    total_active = CaseModel.objects.filter(
        group__isnull=False
    ).exclude(status__in=['Resolved', 'Closed']).count()

    for group in groups:
        count = CaseModel.objects.filter(
            group=group
        ).exclude(status__in=['Resolved', 'Closed']).count()
        dept_stats.append({'name': group.name, 'count': count})

    return JsonResponse({
        'departments': dept_stats,
        'total_all': total_active   # now equals sum of department counts
    })
# NEW: Enhanced case listing with filters (status, level, department)

from django.db.models import Count


@login_required
def get_filtered_cases_api(request):
    app_key = get_app_from_request(request)
    CaseModel = APP_CONFIG[app_key]['case_model']
    queryset = CaseModel.objects.select_related('group', 'subgroup', 'category').all().order_by('-created_at')

    status = request.GET.get('status')
    status_in = request.GET.get('status__in')
    if status_in:
        status_list = [s.strip() for s in status_in.split(',')]
        queryset = queryset.filter(status__in=status_list)
    elif status:
        queryset = queryset.filter(status=status)

    level = request.GET.get('level')
    if level:
        queryset = queryset.filter(current_level=level)

    department = request.GET.get('department')
    if department and department != 'all':
        queryset = queryset.filter(group__name=department)

    subgroup = request.GET.get('subgroup')
    if subgroup and subgroup != 'all':
        queryset = queryset.filter(subgroup_id=subgroup)

    # ─── Category filter ──────────────────────────────────────────
    category = request.GET.get('category')
    if category and category != 'all':
        queryset = queryset.filter(category__name=category)

    # Department counts for the filtered queryset
    dept_counts = queryset.values('group__name').annotate(count=Count('id')).order_by('-count')
    department_counts = [{'name': item['group__name'], 'count': item['count']} for item in dept_counts]

    cases = queryset[:200]

    case_list = [{
        'case_id': c.case_id,
        'customer_name': c.customer_name,
        'mobile': c.mobile,
        'loan_number': c.loan_number,
        'group_name': c.group.name if c.group else None,
        'subgroup_name': c.subgroup.name if c.subgroup else None,
        'category_name': c.category.name if c.category else None,   # NEW
        'priority': c.priority,
        'current_level': c.current_level,
        'status': c.status,
        'created_at': c.created_at.isoformat(),
    } for c in cases]

    return JsonResponse({
        'success': True,
        'cases': case_list,
        'department_counts': department_counts,
    })
# Keep original endpoints for backward compatibility
@login_required
def search_cases_api(request):
    app_key = get_app_from_request(request)
    CaseModel = APP_CONFIG[app_key]['case_model']
    query = request.GET.get('q', '').strip()
    if not query:
        return JsonResponse({'success': False, 'error': 'No search query provided'})
    
    cases = CaseModel.objects.select_related('group', 'subgroup', 'category').filter(
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
        'group_name': c.group.name if c.group else None,
        'subgroup_name': c.subgroup.name if c.subgroup else None,
        'category_name': c.category.name if c.category else None,
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
            'vehicle_number': case.vehicle_number,
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
            'group_id': case.group.id if case.group else None,
            'subgroup_name': case.subgroup.name if case.subgroup else None,
            'subgroup_id': case.subgroup.id if case.subgroup else None,
            'category_name': case.category.name if case.category else None,   # NEW
            'category_id': case.category.id if case.category else None,       # NEW
        }
    })

# adminpanel/views.py

from messaging2.tasks import send_ticket_close_message 

@csrf_exempt
@require_http_methods(["POST"])
def close_case_api(request, case_id):
    agent = get_agent_from_user(request.user)
    if not agent.has_close_permission():
        return JsonResponse(
                {'error': 'You do not have permission to close cases'},
                status=403
            )

    # if agent.role not in ['ADMIN', 'MANAGER']:
    #     return JsonResponse({'error': 'Only Admin and Manager can close cases'}, status=403)

    app_key = get_app_from_request(request)
    cfg = APP_CONFIG[app_key]
    CaseModel = cfg['case_model']
    ContactModel = cfg['contact_model']
    channel_group = cfg['channel_group']

    case = get_object_or_404(CaseModel, case_id=case_id)
    data = json.loads(request.body)

    # This will call the model's close() method – you already allow MANAGER
    case.close(agent, data.get('close_reason', ''))
    # send_ticket_close_message.delay(app_key, case.id)
    # ✅ Update contact model
    ContactModel.objects.filter(mobile=case.mobile).update(
        current_level='CLOSED',
        last_status='Closed'
    )

    # ✅ Broadcast WebSocket update
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        channel_group,
        {
            "type": "contact.update",
            "contact": {
                "mobile": case.mobile,
                "current_level": 'CLOSED',
                "last_status": 'Closed',
                "last_msg": f"✅ Ticket closed: {case.case_id}",
                "last_time": timezone.now().isoformat(),
            }
        }
    )

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


from messaging2.tasks import send_ticket_close_message   # import the task

@csrf_exempt
@require_http_methods(["POST"])
def resolve_case_api(request, case_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        CaseModel, ContactModel, _, channel_group = get_models_for_app(request)

        agent = get_agent_from_user(request.user)
        if not agent.has_resolve_permission():
            return JsonResponse(
                {'error': 'You do not have permission to resolve cases'},
                status=403
            )

        case = CaseModel.objects.get(case_id=case_id)

        if case.status in ['Resolved', 'Closed']:
            return JsonResponse(
                {'error': f'Case already {case.status}'},
                status=400
            )

        data = json.loads(request.body)
        resolution_notes = data.get('resolution_notes', '')

        # Use model method
        case.resolve(
            agent=agent,
            resolution_notes=resolution_notes
        )

        # Update Contact
        ContactModel.objects.filter(
            mobile=case.mobile
        ).update(
            current_level='RESOLVED'
        )

        # WebSocket Broadcast
        channel_layer = get_channel_layer()

        async_to_sync(channel_layer.group_send)(
            channel_group,
            {
                "type": "contact.update",
                "contact": {
                    "mobile": case.mobile,
                    "current_level": "RESOLVED"
                }
            }
        )

        # Send Close Message
        app_key = request.GET.get('app', 'psf')

        send_ticket_close_message.delay(
            app_key,
            case.id
        )

        return JsonResponse({
            'success': True,
            'message': 'Case resolved successfully',
            'case': {
                'case_id': case.case_id,
                'status': case.status,
                'current_level': case.current_level,
                'resolved_at_level': case.resolved_at_level,
                'resolved_by_role': case.resolved_by_role
            }
        })

    except CaseModel.DoesNotExist:
        return JsonResponse(
            {'error': 'Case not found'},
            status=404
        )

    except Exception as e:
        return JsonResponse(
            {'error': str(e)},
            status=500
        )

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


import logging
logger = logging.getLogger(__name__)

@csrf_exempt
@require_http_methods(["POST"])
def edit_case_api(request, case_id):
    try:
        agent = get_agent_from_user(request.user)
        if not agent.has_edit_permission():
            return JsonResponse({'error': 'You do not have permission to edit cases'}, status=403)

        app_key = get_app_from_request(request)
        CaseModel = APP_CONFIG[app_key]['case_model']
        case = get_object_or_404(CaseModel, case_id=case_id)

        data = json.loads(request.body)
        logger.info(f"Editing case {case_id} | data: {data}")

        old_description = case.issue_description
        description_changed = False
        new_description_value = None

        if 'issue_description' in data and data['issue_description'] != old_description:
            description_changed = True
            new_description_value = data['issue_description']

        # ─── Metadata fields ──────────────────────────
        if 'loan_number' in data:
            case.loan_number = data['loan_number']
        if 'vehicle_number' in data:
            case.vehicle_number = data['vehicle_number']
        if 'customer_name' in data:
            case.customer_name = data['customer_name']
        if 'issue_description' in data:
            case.issue_description = data['issue_description']

        # ─── Group change ─────────────────────────────
        group_changed = False
        if 'group' in data:
            group_val = data['group']
            group_obj = None
            if isinstance(group_val, int) or (isinstance(group_val, str) and group_val.isdigit()):
                group_obj = SupportGroup.objects.filter(id=int(group_val)).first()
            elif isinstance(group_val, str):
                group_obj = SupportGroup.objects.filter(name=group_val).first()
            if group_obj:
                if case.group != group_obj:
                    group_changed = True
                case.group = group_obj
            else:
                return JsonResponse({'error': 'Invalid group specified'}, status=400)

        # ─── Subgroup change ──────────────────────────
        if 'subgroup' in data:
            subgroup_val = data['subgroup']
            if subgroup_val:
                try:
                    subgroup_obj = Subgroup.objects.get(id=int(subgroup_val))
                    if case.group and subgroup_obj.group != case.group:
                        return JsonResponse({'error': 'Subgroup does not belong to the selected group'}, status=400)
                    case.subgroup = subgroup_obj
                except (ValueError, Subgroup.DoesNotExist):
                    return JsonResponse({'error': 'Invalid subgroup ID'}, status=400)
            else:
                case.subgroup = None

        # ─── Category change ──────────────────────────
        if 'category' in data:
            category_name = data['category'].strip() if data['category'] else ''
            if category_name:
                category_obj = Category.objects.filter(name=category_name).first()
                if category_obj:
                    if case.group and category_obj.group != case.group:
                        return JsonResponse({'error': 'Category does not belong to the selected group'}, status=400)
                    case.category = category_obj
                else:
                    return JsonResponse({'error': f'Category "{category_name}" not found'}, status=400)
            else:
                case.category = None

        # ─── If group changed, reassign and clear orphaned relations ──
        if group_changed:
            # Clear subgroup/category if they don't belong to the new group
            if case.subgroup and case.subgroup.group_id != case.group_id:
                case.subgroup = None
            if case.category and case.category.group_id != case.group_id:
                case.category = None

            try:
                from messaging2.views import auto_assign
                auto_assign(case)
                case.assigned_to_name = case.assigned_to.name if case.assigned_to else None
            except Exception as e:
                logger.error(f"auto_assign failed: {e}")

        # ─── Save ──────────────────────────────────────
        case.save(update_fields=['loan_number', 'customer_name', 'issue_description','vehicle_number',
                                 'group', 'subgroup', 'category', 'assigned_to_name', 'updated_at'])
        logger.info(f"Case {case_id} saved successfully")
        app_key = get_app_from_request(request)
        DescriptionLogModel = APP_CONFIG[app_key]['description_log_model']
        # ─── Description log ──────────────────────────
        if description_changed:
            DescriptionLogModel.objects.create(
                case=case,
                previous_description=old_description or "",
                new_description=new_description_value,
                changed_by=agent.name or "Unknown",
                changed_by_role=agent.role,
                level=case.current_level,
            )

        # ─── Return updated data ──────────────────────
        return JsonResponse({
            'success': True,
            'message': 'Case updated',
            'case': {
                'group_id': case.group_id,
                'group_name': case.group.name if case.group else None,
                'subgroup_id': case.subgroup_id,
                'subgroup_name': case.subgroup.name if case.subgroup else None,
                'category_id': case.category_id,
                'category_name': case.category.name if case.category else None,
                'issue_description': case.issue_description,
                'loan_number': case.loan_number,
                'vehicle_number':case.vehicle_number,
                'customer_name': case.customer_name,
                'assigned_to_name': case.assigned_to_name,
            }
        })

    except Exception as e:
        logger.error(f"Error in edit_case_api: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)

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


import pandas as pd
from io import BytesIO
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import datetime

# Import both case models
from messaging2.models import Case as psfCase
from messaging.models import Case as smsCase

@login_required
def download_user_cases_excel(request, user_id):
    # Admin permission check
    agent = get_agent_from_user(request.user)
    if agent.role != 'ADMIN':
        return HttpResponse("Access denied. Admin only.", status=403)

    user = get_object_or_404(User, id=user_id)
    username = user.username

    # Fetch cases from both apps (using only necessary fields)
    psf_cases = psfCase.objects.filter(created_by=username).values(
        'case_id', 'customer_name', 'mobile', 'loan_number', 'vehicle_number',
        'group__name', 'subgroup__name', 'category__name', 'current_level',
        'status', 'priority', 'created_at', 'resolved_at', 'closed_at',
        'issue_description', 'resolution_notes', 'source','source_app'
    )
    
    sms_cases = smsCase.objects.filter(created_by=username).values(
        'case_id', 'customer_name', 'mobile', 'loan_number', 'vehicle_number',
        'group__name', 'subgroup__name', 'category__name', 'current_level',
        'status', 'priority', 'created_at', 'resolved_at', 'closed_at',
        'issue_description', 'resolution_notes', 'source','source_app'
    )

    def format_datetime(dt):
        """Convert datetime to formatted string with AM/PM, handling None."""
        if dt is None:
            return ''
        # If timezone-aware, make it naive
        if timezone.is_aware(dt):
            dt = timezone.localtime(dt)  # convert to local timezone
            dt = dt.replace(tzinfo=None)  # remove timezone info
        # Format as dd-mm-yyyy hh:mm AM/PM
        return dt.strftime('%d-%m-%Y %I:%M %p')

    def process_queryset(qs, app_name):
        data = list(qs)
        for row in data:
            row['App'] = app_name
            # Rename foreign key fields
            row['Group'] = row.pop('group__name', '')
            row['Subgroup'] = row.pop('subgroup__name', '')
            row['Category'] = row.pop('category__name', '')
            # Format datetime fields
            for field in ['created_at', 'resolved_at', 'closed_at']:
                if field in row:
                    row[field] = format_datetime(row[field])
            # Ensure blank values for None
            for key, val in row.items():
                if val is None:
                    row[key] = ''
        return data

    combined = process_queryset(psf_cases, 'PSF') + process_queryset(sms_cases, 'SMS')

    if not combined:
        df = pd.DataFrame([{'Message': f'No cases found for {username}'}])
    else:
        df = pd.DataFrame(combined)
        # Reorder columns – put 'App' first
        cols = ['App'] + [c for c in df.columns if c != 'App']
        df = df[cols]

    # Generate Excel file
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Cases')
    output.seek(0)

    response = HttpResponse(
        output.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="cases_{username}_{timezone.now().strftime("%Y%m%d_%H%M")}.xlsx"'
    return response




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

import re

def validate_password_strength(password):
    """
    Returns a list of error messages if password is invalid.
    Returns an empty list if password meets all requirements.
    """
    errors = []
    if len(password) < 6:
        errors.append("Password must be at least 6 characters long.")
    if not re.search(r'[A-Za-z]', password):
        errors.append("Password must contain at least one letter.")
    if not re.search(r'\d', password):
        errors.append("Password must contain at least one digit.")
    if not re.search(r'[^A-Za-z0-9]', password):
        errors.append("Password must contain at least one special character (e.g., @, #, $).")
    return errors

@login_required
def user_create(request):
    agent = get_agent_from_user(request.user)
    if agent.role != 'ADMIN':
        messages.error(request, "Access denied. Admin only.")
        return redirect('agent_dashboard')

    groups = SupportGroup.objects.all().order_by('name')
    subgroups = Subgroup.objects.all().order_by('name')

    # Helper to build context from POST data (for re‑rendering)
    def build_context(post):
        return {
            'role_choices': Agent.ROLE_CHOICES,
            'groups': groups,
            'subgroups': subgroups,
            # Field values
            'username': post.get('username', ''),
            'email': post.get('email', ''),
            'mobile': post.get('mobile', ''),
            'name': post.get('name', ''),
            'role': post.get('role', 'AGENT'),
            'can_edit': post.get('can_edit') == 'on',
            'can_resolve': post.get('can_resolve') == 'on',
            'can_close': post.get('can_close') == 'on',
            # Preserve selections
            'selected_groups': post.getlist('groups'),
            'selected_subgroups': post.getlist('subgroups'),
        }

    if request.method == "POST":
        username = request.POST.get('username')
        password = request.POST.get('password')
        email = request.POST.get('email', '')
        role = request.POST.get('role', 'AGENT')
        mobile = request.POST.get('mobile', '')
        display_name = request.POST.get('name', '')
        selected_groups = request.POST.getlist('groups')
        selected_subgroups = request.POST.getlist('subgroups')

        # ─── 1️⃣ PASSWORD VALIDATION ───────────────────────────────
        password_errors = validate_password_strength(password)
        if password_errors:
            for err in password_errors:
                messages.error(request, err)
            return render(request, 'adminpanel/user_create.html', build_context(request.POST))

        # ─── 2️⃣ OTHER CHECKS ──────────────────────────────────────
        # (username exists, subgroups validation, etc.)
        if User.objects.filter(username=username).exists():
            messages.error(request, "Username already exists")
            return render(request, 'adminpanel/user_create.html', build_context(request.POST))

        # Subgroup validation (unchanged)
        if selected_groups:
            allowed_subgroup_ids = Subgroup.objects.filter(
                group__id__in=selected_groups
            ).values_list('id', flat=True)
            selected_subgroup_ids = [int(sid) for sid in selected_subgroups if sid.isdigit()]
            invalid_subgroups = set(selected_subgroup_ids) - set(allowed_subgroup_ids)
            if invalid_subgroups:
                selected_subgroups = [str(sid) for sid in selected_subgroup_ids if sid in allowed_subgroup_ids]
                messages.warning(request, "Some invalid subgroups were removed.")
        else:
            if selected_subgroups:
                messages.error(request, "You must select at least one group to assign subgroups.")
                selected_subgroups = []

        # ─── 3️⃣ CREATE USER ──────────────────────────────────────
        with transaction.atomic():
            is_staff = role in ['ADMIN', 'MANAGER']
            user = User.objects.create_user(
                username=username,
                password=password,
                email=email,
                is_staff=is_staff,
            )
            agent_obj = Agent.objects.create(
                user=user,
                agent_id=f"AGT-{user.id}",
                name=display_name or username,
                email=email,
                mobile=mobile,
                role=role,
                can_edit=request.POST.get('can_edit') == 'on',
                can_resolve=request.POST.get('can_resolve') == 'on',
                can_close=request.POST.get('can_close') == 'on',
            )
            agent_obj.groups.set(selected_groups)
            agent_obj.subgroup.set(selected_subgroups)

        messages.success(request, f"User '{username}' created successfully")
        return redirect('admin_user_list')

    # GET – empty form
    return render(request, 'adminpanel/user_create.html', {
        'role_choices': Agent.ROLE_CHOICES,
        'groups': groups,
        'subgroups': subgroups,
    })


@login_required
def user_edit(request, user_id):
    agent = get_agent_from_user(request.user)

    if agent.role != 'ADMIN':
        messages.error(request, "Access denied.")
        return redirect('agent_dashboard')

    user = get_object_or_404(User, id=user_id)
    user_agent = Agent.objects.filter(user=user).first()

    groups = SupportGroup.objects.all().order_by('name')
    subgroups = Subgroup.objects.all().order_by('name')

    if request.method == "POST":
        username = request.POST.get('username')
        email = request.POST.get('email', '')
        role = request.POST.get('role', 'AGENT')
        mobile = request.POST.get('mobile', '')
        display_name = request.POST.get('name', '')

        selected_groups = request.POST.getlist('groups')
        selected_subgroups = request.POST.getlist('subgroups')

        # ─── New permission flags ───────────────────────────────
        can_edit = request.POST.get('can_edit') == 'on'
        can_resolve = request.POST.get('can_resolve') == 'on'
        can_close = request.POST.get('can_close') == 'on'

        # --- Server-side validation for subgroups ---
        if selected_groups:
            allowed_subgroup_ids = Subgroup.objects.filter(
                group__id__in=selected_groups
            ).values_list('id', flat=True)
            
            selected_subgroup_ids = [int(sid) for sid in selected_subgroups if sid.isdigit()]
            invalid_subgroups = set(selected_subgroup_ids) - set(allowed_subgroup_ids)
            
            if invalid_subgroups:
                selected_subgroups = [str(sid) for sid in selected_subgroup_ids if sid in allowed_subgroup_ids]
                messages.warning(request, "Some invalid subgroups were removed because they don't belong to any selected group.")
        else:
            if selected_subgroups:
                messages.error(request, "You must select at least one group to assign subgroups.")
                selected_subgroups = []

        # Update user
        user.username = username
        user.email = email
        user.is_staff = role in ['ADMIN', 'MANAGER']
        pwd = request.POST.get('password', '').strip()

# Validate password only if a new password is entered
        if pwd:
            password_errors = validate_password_strength(pwd)
            if password_errors:
                for error in password_errors:
                    messages.error(request, error)

                return render(request, 'adminpanel/user_edit.html', {
                    'user': user,
                    'user_agent': user_agent,
                    'role_choices': Agent.ROLE_CHOICES,
                    'groups': groups,
                    'subgroups': subgroups,
                })
            user.set_password(pwd)
        user.save()

        # Update agent
        if user_agent:
            user_agent.role = role
            user_agent.name = display_name or username
            user_agent.email = email
            user_agent.mobile = mobile
            user_agent.can_edit = can_edit
            user_agent.can_resolve = can_resolve
            user_agent.can_close = can_close
            user_agent.save()
            user_agent.groups.set(selected_groups)
            user_agent.subgroup.set(selected_subgroups)
        else:
            user_agent = Agent.objects.create(
                user=user,
                agent_id=f"AGT-{user.id}",
                name=display_name or username,
                email=email,
                mobile=mobile,
                role=role,
                is_active=True,
                can_edit=can_edit,
                can_resolve=can_resolve,
                can_close=can_close,
            )
            user_agent.groups.set(selected_groups)
            user_agent.subgroup.set(selected_subgroups)

        messages.success(request, "User updated successfully")
        return redirect('admin_user_list')

    return render(request, 'adminpanel/user_edit.html', {
        'user': user,
        'user_agent': user_agent,
        'role_choices': Agent.ROLE_CHOICES,
        'groups': groups,
        'subgroups': subgroups,
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
