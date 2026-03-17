"""
Django settings for whatsapp_sender project.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# -------------------------------------------------------
# LOAD ENV VARIABLES
# -------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# -------------------------------------------------------
# SECURITY
# -------------------------------------------------------
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY")

DEBUG = False

ALLOWED_HOSTS = [
    "padmasai.info",
    "www.padmasai.info",
    "localhost",
    "127.0.0.1",
    "65.2.185.167",
    ".ap-south-1.compute.amazonaws.com",
]

# -------------------------------------------------------
# INSTALLED APPS
# -------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    "channels",
    "storages",

    "adminpanel",
    "messaging",
    "messaging2",
    "financehub",
]

# -------------------------------------------------------
# MIDDLEWARE
# -------------------------------------------------------
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

LOGIN_URL = "/adminpanel/login/"
LOGIN_REDIRECT_URL = "/adminpanel/dashboard/"

# -------------------------------------------------------
# TEMPLATES
# -------------------------------------------------------
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

# -------------------------------------------------------
# DATABASE
# -------------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": os.getenv("DB_NAME"),
        "USER": os.getenv("DB_USER"),
        "PASSWORD": os.getenv("DB_PASSWORD"),
        "HOST": os.getenv("DB_HOST"),
        "PORT": "3306",
        "OPTIONS": {
            "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
            "charset": "utf8mb4",
        },
    }
}

# -------------------------------------------------------
# PASSWORD VALIDATION
# -------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# -------------------------------------------------------
# LANGUAGE / TIMEZONE
# -------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

# -------------------------------------------------------
# STATIC FILES
# -------------------------------------------------------
STATIC_URL = "/static/"
STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")

# -------------------------------------------------------
# MEDIA FILES
# -------------------------------------------------------
MEDIA_URL = "/media/"
MEDIA_ROOT = os.path.join(BASE_DIR, "media")

# -------------------------------------------------------
# DEFAULT PRIMARY KEY
# -------------------------------------------------------
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# -------------------------------------------------------
# WHATSAPP APP 1
# -------------------------------------------------------
WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
WHATSAPP_BUSINESS_ACCOUNT_ID = os.getenv("WHATSAPP_BUSINESS_ACCOUNT_ID")
WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN")

# -------------------------------------------------------
# WHATSAPP APP 2
# -------------------------------------------------------
WHATSAPP2_ACCESS_TOKEN = os.getenv("WHATSAPP2_ACCESS_TOKEN")
WHATSAPP2_PHONE_NUMBER_ID = os.getenv("WHATSAPP2_PHONE_NUMBER_ID")
WHATSAPP2_BUSINESS_ACCOUNT_ID = os.getenv("WHATSAPP2_BUSINESS_ACCOUNT_ID")
WHATSAPP2_VERIFY_TOKEN = os.getenv("WHATSAPP2_VERIFY_TOKEN")

# -------------------------------------------------------
# AWS S3 STORAGE
# -------------------------------------------------------
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_STORAGE_BUCKET_NAME = os.getenv("AWS_STORAGE_BUCKET_NAME")

AWS_S3_REGION_NAME = "ap-south-1"
AWS_S3_SIGNATURE_VERSION = "s3v4"

AWS_DEFAULT_ACL = None
AWS_S3_FILE_OVERWRITE = False
AWS_S3_VERIFY = True
AWS_S3_ADDRESSING_STYLE = "virtual"

DEFAULT_FILE_STORAGE = "storages.backends.s3boto3.S3Boto3Storage"

# -------------------------------------------------------
# LEGAL PDF LOCATION
# -------------------------------------------------------
LEGAL_PDF_DIR = BASE_DIR / "legal_pdfs"

# -------------------------------------------------------
# CELERY + REDIS
# -------------------------------------------------------
CELERY_BROKER_URL = "redis://127.0.0.1:6379/0"
CELERY_RESULT_BACKEND = "redis://127.0.0.1:6379/2"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "Asia/Kolkata"

CELERY_TASK_ROUTES = {
    "messaging.tasks.*": {"queue": "whatsapp_main"},
    "messaging2.tasks.*": {"queue": "whatsapp_secondary"},
    "financehub.tasks.*": {"queue": "whatsapp_main"},
}

# -------------------------------------------------------
# CSRF
# -------------------------------------------------------
APPEND_SLASH = False

CSRF_TRUSTED_ORIGINS = [
    "https://chemiluminescent-giselle-numinously.ngrok-free.dev",
]

# -------------------------------------------------------
# FILE UPLOAD DIRECTORIES
# -------------------------------------------------------
UPLOAD_DIR_1 = os.path.join(BASE_DIR, "uploads")
UPLOAD_DIR_2 = os.path.join(BASE_DIR, "uploads2")

os.makedirs(UPLOAD_DIR_1, exist_ok=True)
os.makedirs(UPLOAD_DIR_2, exist_ok=True)

# -------------------------------------------------------
# CHANNELS
# -------------------------------------------------------
ASGI_APPLICATION = "whatsapp_sender.asgi.application"

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [("127.0.0.1", 6379, 1)],
        },
    },
}
