from django.urls import path
from . import views

urlpatterns = [

    # ---------------- AUTH ----------------
    path("login/", views.fh_login, name="fh_login"),
    path("logout/", views.fh_logout, name="fh_logout"),

    # ---------------- UPLOAD ----------------
    path("upload-loan-data/", views.upload_loan_data, name="upload_loan_data"),
    path("upload-progress/<int:upload_id>/", views.upload_progress, name="upload_progress"),

    # ---------------- LCC ----------------
    path("lcc-data/", views.lcc_list, name="lcc_list"),
    path("lcc-delete/", views.lcc_delete, name="lcc_delete"),
    path("ca-delete/", views.cA_delete, name="ca_delete"),
    path("repo-delete/", views.repo_delete, name="repo_delete"),
    path("closed-delete/", views.closed_delete, name="closed_delete"),
    path("paid-delete/", views.paid_delete, name="paid_delete"),

    # ---------------- FEEDBACK ----------------
    path("feedback/", views.feedback_list, name="feedback_list"),
    path("feedback/add/", views.feedback_create, name="feedback_create"),

    # ---------------- ADMIN : VISIT SCHEDULE ----------------
    path(
        "executive-visit-schedule/",
        views.executive_visit_schedule_list,
        name="executive_visit_schedule_list",
    ),
    path(
        "executive-visit-schedule/edit/<int:pk>/",
        views.executive_visit_schedule_edit,
        name="executive_visit_schedule_edit",
    ),

    # ---------------- EXECUTIVE ----------------
    path(
        "executive/my-visits/",
        views.executive_my_visits,
        name="executive_my_visits",
    ),
    path(
        "executive/visit-response/<int:pk>/",
        views.executive_visit_response,
        name="executive_visit_response",
    ),

    path("due-notices/", views.due_notice_list, name="due_notice_list"),
      
      


]
