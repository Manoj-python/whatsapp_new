from django.urls import path
from .views import upload_excel

urlpatterns = [
    path('', upload_excel, name='upload_excel'),
]
