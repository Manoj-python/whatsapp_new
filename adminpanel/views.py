from django.shortcuts import render

# Create your views here.
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages

def login_view(request):
    if request.method == "POST":
        username = request.POST.get('username')
        password = request.POST.get('password')

        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            return redirect('admin_dashboard')
        else:
            messages.error(request, "Invalid login")

    return render(request, 'adminpanel/login.html')


def logout_view(request):
    logout(request)
    return redirect('admin_login')


@login_required
def dashboard(request):
    users = User.objects.all().order_by('id')
    return render(request, 'adminpanel/dashboard.html', {
        'users': users
    })


@login_required
def user_list(request):
    users = User.objects.all()
    return render(request, 'adminpanel/user_list.html', {
        'users': users
    })


@login_required
def user_create(request):
    if request.method == "POST":
        username = request.POST['username']
        password = request.POST['password']
        is_staff = request.POST.get('is_staff') == "on"

        if User.objects.filter(username=username).exists():
            messages.error(request, "Username already exists")
        else:
            User.objects.create_user(username=username, password=password, is_staff=is_staff)
            messages.success(request, "User created")
            return redirect('admin_user_list')

    return render(request, 'adminpanel/user_create.html')


@login_required
def user_edit(request, user_id):
    user = get_object_or_404(User, id=user_id)

    if request.method == "POST":
        user.username = request.POST['username']
        user.is_staff = request.POST.get('is_staff') == "on"

        pwd = request.POST.get('password')
        if pwd:
            user.set_password(pwd)

        user.save()
        messages.success(request, "User updated")
        return redirect('admin_user_list')

    return render(request, 'adminpanel/user_edit.html', {
        'user': user
    })


@login_required
def user_delete(request, user_id):
    get_object_or_404(User, id=user_id).delete()
    messages.success(request, "User deleted")
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
