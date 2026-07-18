from django.urls import path

from portal.views import auth, dashboard, dev, payments

urlpatterns = [
    path("", dashboard.index, name="index"),
    path("login", auth.login_page, name="login"),
    path("login/send-otp", auth.send_otp, name="send_otp"),
    path("login/resend-otp", auth.resend_otp, name="resend_otp"),
    path("login/verify-otp", auth.verify_otp, name="verify_otp"),
    path("login/agreement", auth.agreement_dispatch, name="agreement_login"),
    path("logout", auth.logout, name="logout"),
    path("lang/<str:code>", auth.set_lang, name="set_lang"),
    path("dashboard", dashboard.dashboard, name="dashboard"),
    path("loan/<str:finance_id>", dashboard.loan_detail, name="loan_detail"),
    path("loan/<str:finance_id>/pay", payments.pay_page, name="pay_page"),
    path("loan/<str:finance_id>/pay/qr", payments.generate_qr, name="generate_qr"),
    path("payment/<int:txn_id>/receipt.pdf", payments.receipt_pdf, name="receipt_pdf"),
    path("dev/lms-probe", dev.lms_probe, name="lms_probe"),
]
