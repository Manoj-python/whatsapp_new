from django.urls import path
from .views import *

urlpatterns = [
    
    path("upload-data/", upload_data, name="upload_data"),
    path("upload-spl-progress/<int:upload_id>/", upload_spl_progress, name="upload_spl_progress"),

    path("get-lcc-details/", lcc_detail_list, name="lcc_details"),
    path("get-writeoff-details/", write_off_list, name="writeoff_details"),
    path("get-ledger-details/", ledger_list, name="ledger_details"),
    path("get-auction-details/", auction_list, name="auction_details"),
    path("get-dealer-details/", dealer_list, name="dealer_details"),


    path("upload/",upload_and_send3,name="upload"),

    path('job2/<str:job_id>/', job_status3, name='job_status3'),
    path('download-success2/<str:job_id>/', download_success_report3, name='download_success_report3'),
    path('download-failed2/<str:job_id>/', download_failed_report3, name='download_failed_report3'),

    path("chat3/", chat_dashboard3, name="chat_dashboard3"),
    path("api/messages3/<str:mobile>/", chat_messages_api3, name="chat_messages_api3"),
    path("api/send-reply3/", send_reply_api3, name="send_reply_api3"),
    path("api/mark-read3/<str:mobile>/", mark_read3),
    path("login3/", messaging3_login, name="splcase_login"),
    path("logout3/", messaging3_logout, name="splcase_logout"),

    path("api/contacts3/", contacts_api3, name="contacts_api3"),
    # path("api/refresh-media/", refresh_media, name="refresh-media"),
    # path("api/stream-media/", stream_media),
    path("webhook/", whatsapp_webhook3, name="whatsapp_webhook3"),
    path("api/mark-read3/<str:mobile>/", mark_read3, name="mark_read3"),
   
    path('api/contact-messages3/', get_contact_messages3, name='get_contact_messages3'),
    path('secure-document3/<int:log_id>/', view_secure_document3, name='secure_document3'),





]




