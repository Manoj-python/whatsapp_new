"""
URL configuration for whatsapp_sender project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path,include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('',include('messaging.urls')),
    path('messaging2/',include('messaging2.urls')),
    path('adminpanel/', include('adminpanel.urls')),
    path('financehub/', include('financehub.urls')),
    path('notice/', include('notices.urls')),
    path('splcases_app/', include('special_cases.urls')),
    # path('sms_app/', include('sms_app.urls')),
    path('meghaai/', include('meghaai_app.urls')),    
    path('batch/', include('batch_app.urls')), 


]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
