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
