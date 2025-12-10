from django.urls import path
from .views import fh_login, fh_logout, upload_loan_data, lcc_list, feedback_list, feedback_create

urlpatterns = [
    # FinanceHub Authentication
    path("login/", fh_login, name="fh_login"),
    path("logout/", fh_logout, name="fh_logout"),

    # App Views
    path("upload-loan-data/", upload_loan_data, name="upload_loan_data"),
    path("lcc-data/", lcc_list, name="lcc_list"),
    path("feedback/", feedback_list, name="feedback_list"),
    path("feedback/add/", feedback_create, name="feedback_create"),

]
