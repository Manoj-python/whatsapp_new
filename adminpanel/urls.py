from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='admin_dashboard'),
    path('login/', views.login_view, name='admin_login'),
    path('logout/', views.logout_view, name='admin_logout'),

    # User management
    path('users/', views.user_list, name='admin_user_list'),
    path('users/create/', views.user_create, name='admin_user_create'),
    path('users/edit/<int:user_id>/', views.user_edit, name='admin_user_edit'),
    path('users/delete/<int:user_id>/', views.user_delete, name='admin_user_delete'),
]

