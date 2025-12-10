"""
Django settings for whatsapp_sender project.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------
# SECURITY & DEBUG
# ---------------------------------------------------------------------
SECRET_KEY = 'django-insecure-&ec&(!u@z9b7of8+l$rm74f)zptc9o-(2-4wk4r+cb6w80a-1h'
DEBUG = False

ALLOWED_HOSTS = ["padmasai.info", "www.padmasai.info", "localhost", "127.0.0.1"]

# ---------------------------------------------------------------------
# INSTALLED APPS
# ---------------------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles", 
     "channels", 
     "storages",
     'adminpanel',

     "messaging",
     "messaging2",
     "financehub",
]

# ---------------------------------------------------------------------
# MIDDLEWARE
# ---------------------------------------------------------------------
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "whatsapp_sender.urls"


LOGIN_URL = '/adminpanel/login/'
LOGIN_REDIRECT_URL = '/adminpanel/dashboard/'

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "whatsapp_sender.wsgi.application"

# ---------------------------------------------------------------------
# DATABASE
# ---------------------------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": "whatsappdb",
        "USER": "django",
        "PASSWORD": "DjangoDBpass123!",
        "HOST": "127.0.0.1",
        "PORT": "3306",
        "OPTIONS": {
            "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
            "charset": "utf8mb4",
        },
    }
}

# ---------------------------------------------------------------------
# PASSWORD VALIDATION
# ---------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------
# LANGUAGE, TIMEZONE
# ---------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------
# STATIC & MEDIA
# ---------------------------------------------------------------------
STATIC_URL = "/static/"
STATIC_ROOT = os.path.join(BASE_DIR, "static")

MEDIA_URL = "/media/"
MEDIA_ROOT = os.path.join(BASE_DIR, "media")

# ---------------------------------------------------------------------
# DEFAULT PRIMARY KEY
# ---------------------------------------------------------------------
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------
# WHATSAPP API CREDENTIALS (App 1)
# ---------------------------------------------------------------------
WHATSAPP_ACCESS_TOKEN = os.environ.get(
    "WHATSAPP_ACCESS_TOKEN",
    "EAAQJIMeFEA0BPstK4UJZBZCa1RDUXk9HCGrlgydJhJnKAJnAlvZAmLLD9qx7T5hQioN50oECZC8msUZBZCD3o1gytncqKR6PoOCLCPGeJdXgG3TVuMVaoEsxcpwkZCsU7dAi2KQGG2kKgQR4LL5k61d7Qlaq7RK5PSTnYLlezrmxLilJZC6ZBYAUGwRcCVOS4EaMEGEuYSOGZCZC2QNygqbIuXQjMkJpTwGuLxeKNIS",
)
WHATSAPP_PHONE_NUMBER_ID = os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "238505906024065")
WHATSAPP_BUSINESS_ACCOUNT_ID = "284960064705398"
WHATSAPP_VERIFY_TOKEN = os.environ.get("WHATSAPP_VERIFY_TOKEN", "smsquare_verify_123567")

# ---------------------------------------------------------------------
# WHATSAPP API CREDENTIALS (App 2)
# ---------------------------------------------------------------------
WHATSAPP2_ACCESS_TOKEN = os.environ.get(
    "WHATSAPP2_ACCESS_TOKEN",
    "EAAFDTYZCppQIBP6OFQkMtpWA1WjOFTtOxcZBQoE5YT3rgsZCqZBcqJZB74KJ8ZBP5sRAaRHXhhXfm18sfaBpjONw2xhb7aRMmYeTubweDJwAGhuNSZB6ZClP2HUECaQoAFDeEXY0houpRjX0YHTJZCsKPpoxso6Q9iDKHeZBvOVMHe6qdDx7ZBdRlUODZCyfNi3t6YrZAZCxRUnMnuhF072fcX1G1LuFJnQqgbi7O7xNch",
)
WHATSAPP2_PHONE_NUMBER_ID = os.environ.get("WHATSAPP2_PHONE_NUMBER_ID", "901458883040647")
WHATSAPP2_BUSINESS_ACCOUNT_ID = "1121446340109803"
WHATSAPP2_VERIFY_TOKEN = os.environ.get("WHATSAPP2_VERIFY_TOKEN", "smsquare_verify_2")



# ---------------------------------------------------------------------
# AWS S3 STORAGE CONFIGURATION
# ---------------------------------------------------------------------
AWS_ACCESS_KEY_ID = "AKIA2PW4BLO5V222Z5OX"
AWS_SECRET_ACCESS_KEY = "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"
AWS_STORAGE_BUCKET_NAME = "whatsapp-sender-files"
AWS_S3_REGION_NAME = "ap-south-1"
AWS_S3_SIGNATURE_VERSION = "s3v4"

AWS_DEFAULT_ACL = None
AWS_S3_FILE_OVERWRITE = False
AWS_S3_VERIFY = True

# CRITICAL FIX
AWS_S3_ADDRESSING_STYLE = "virtual"

# Use S3 for all uploaded media (images, documents, WhatsApp media, Excel, etc.)
DEFAULT_FILE_STORAGE = "storages.backends.s3boto3.S3Boto3Storage"



# ---------------------------------------------------------------------
# CELERY + REDIS CONFIG
# ---------------------------------------------------------------------
CELERY_BROKER_URL = "redis://127.0.0.1:6379/0"
CELERY_RESULT_BACKEND = "redis://127.0.0.1:6379/0"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "Asia/Kolkata"

# Optional: define separate queues for each app (optional but cleaner)
CELERY_TASK_ROUTES = {
    "messaging.tasks.*": {"queue": "whatsapp_main"},
    "messaging2.tasks.*": {"queue": "whatsapp_secondary"},
    "financehub.tasks.*": {"queue": "whatsapp_main"},   # NEW
}

# ---------------------------------------------------------------------
# CSRF / NGROK
# ---------------------------------------------------------------------
APPEND_SLASH = False

CSRF_TRUSTED_ORIGINS = [
    "https://chemiluminescent-giselle-numinously.ngrok-free.dev",
]

# ---------------------------------------------------------------------
# FILE UPLOAD LOCATIONS FOR EACH APP
# ---------------------------------------------------------------------
UPLOAD_DIR_1 = os.path.join(BASE_DIR, "uploads")
UPLOAD_DIR_2 = os.path.join(BASE_DIR, "uploads2")

os.makedirs(UPLOAD_DIR_1, exist_ok=True)
os.makedirs(UPLOAD_DIR_2, exist_ok=True)


ASGI_APPLICATION = "whatsapp_sender.asgi.application"

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [("127.0.0.1", 6379)],
        },
    },
}
