import os
from pathlib import Path
from decouple import config, Csv
from celery.schedules import crontab
import dj_database_url

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'umrah-chalo-786-services'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False

ALLOWED_HOSTS = [
    'umrachalo.tawheedumrah.com',
    'www.umrachalo.tawheedumrah.com',
    'umrachalo.com',
    'localhost',
    '127.0.0.1',
    '13.49.76.147',  # IP must be a string
]


# Application definition
DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

THIRD_PARTY_APPS = [
    'rest_framework',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    'drf_spectacular',
    'django_filters',
    'razorpay',
    'phonenumber_field',
    'django_extensions',
    'django_celery_beat',
    'django_cleanup.apps.CleanupConfig',
    'taggit',
    'django_ckeditor_5',
    'imagekit',
    'simple_history',
]

LOCAL_APPS = [
    'apps.core',
    'apps.authentication',
    'apps.services',
    'apps.packages',
    'apps.leads',
    'apps.subscriptions',
    'apps.notifications',
    'apps.payments',
    'apps.reviews',
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'simple_history.middleware.HistoryRequestMiddleware',
]

ROOT_URLCONF = 'umrahchalo.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [
            BASE_DIR / 'templates',
            BASE_DIR / 'templates' / 'notifications', 
        ],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'umrahchalo.wsgi.application'

# Database
# settings.py

DATABASES = {
    'default': {
        'ENGINE': 'mssql',
        'NAME': 'Umrahchalo',
        'USER': 'Umrahchalo',
        'PASSWORD': 'Umrahchalo@54321',
        'HOST': '103.21.58.193',  # Or use Plesk-provided host
        'PORT': '1433',            # Plesk SQL port
        'OPTIONS': {
            'driver': 'ODBC Driver 18 for SQL Server',
            'extra_params': 'TrustServerCertificate=yes;'
        },
    }
}
# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Kolkata'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Custom User Model
AUTH_USER_MODEL = 'authentication.User'

# REST Framework Configuration
REST_FRAMEWORK = {
    
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'apps.core.pagination.CustomPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'DEFAULT_PARSER_CLASSES': [
        'rest_framework.parsers.JSONParser',
        'rest_framework.parsers.MultiPartParser',
        'rest_framework.parsers.FormParser',
    ],
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'EXCEPTION_HANDLER': 'apps.core.exceptions.custom_exception_handler',
}

# Spectacular settings for API documentation
SPECTACULAR_SETTINGS = {
    'TITLE': 'Umrah Chalo API',
    'DESCRIPTION': 'API documentation for Umrah Chalo platform',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'SCHEMA_PATH_PREFIX': '/api/v1/',
    'COMPONENT_SPLIT_REQUEST': True,
    'SORT_OPERATIONS': False,
}

# CORS Settings
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:5173",
    "http://umrachalo.com",]
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:5173",
    "http://umrachalo.com",
]

# Celery Configuration
CELERY_BROKER_URL = config('REDIS_URL', default='redis://localhost:6379/0')
CELERY_RESULT_BACKEND = config('REDIS_URL', default='redis://localhost:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULE = {
    'check-subscription-expiry': {
        'task': 'apps.subscriptions.tasks.check_subscription_expiry',
        'schedule': 60.0 * 60.0,  # Run every hour
    },
    'send-package-upload-reminders': {
        'task': 'apps.notifications.tasks.send_package_upload_reminders',
        'schedule': 60.0 * 60.0 * 24.0,  # Run daily
    },
    'send-daily-notifications': {
        'task': 'apps.notifications.tasks.send_daily_notifications',
        'schedule': crontab(hour=9, minute=0),  # Run daily at 9 AM
    },
}

# Cache Configuration
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': config('REDIS_URL', default='redis://localhost:6379/1'),
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        }
    }
}


# Session Configuration
SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
SESSION_CACHE_ALIAS = 'default'

# Payment Gateway Configuration
RAZORPAY_KEY_ID = 'rzp_test_ZI5G0k0dQJfr79'
RAZORPAY_KEY_SECRET = 'lZUttTsMhykdSWawNeXGC5nG'

# Optional: Webhook secret for signature validation
# You can get this from Razorpay dashboard when setting up webhooks
RAZORPAY_WEBHOOK_SECRET = 'Umrahchalo@786'  # Replace with actual secret

# Payment gateway settings
PAYMENT_GATEWAY_SETTINGS = {
    'RAZORPAY': {
        'KEY_ID': RAZORPAY_KEY_ID,
        'KEY_SECRET': RAZORPAY_KEY_SECRET,
        'WEBHOOK_SECRET': RAZORPAY_WEBHOOK_SECRET if 'RAZORPAY_WEBHOOK_SECRET' in locals() else None,
        'MODE': 'TEST',  # Change to 'LIVE' in production
    }
}
STRIPE_PUBLIC_KEY = config('STRIPE_PUBLIC_KEY', default='')
STRIPE_SECRET_KEY = config('STRIPE_SECRET_KEY', default='')
# Add these to your Django settings.py file

# Email Configuration for Notifications
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'  # or your SMTP server
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = 'your-email@gmail.com'
EMAIL_HOST_PASSWORD = 'your-app-password'
DEFAULT_FROM_EMAIL = 'Umrah Chalo <noreply@umrahchalo.com>'

# Notification System Settings
NOTIFICATION_SETTINGS = {
    'DEFAULT_FROM_EMAIL': DEFAULT_FROM_EMAIL,
    'SUPPORT_EMAIL': 'support@umrahchalo.com',
    'COMPANY_NAME': 'Umrah Chalo',
    'FRONTEND_URL': 'https://your-domain.com',
    'APP_DOWNLOAD_URL': 'https://play.google.com/store/apps/details?id=com.umrahchalo',
    'MAX_RETRIES': 3,
    'RETRY_DELAY_MINUTES': [5, 15, 45],  # Exponential backoff
    'CLEANUP_DAYS': {
        'notifications': 180,  # 6 months
        'logs': 90,  # 3 months
    },
    'DIGEST_SETTINGS': {
        'max_notifications_in_digest': 10,
        'digest_time': {
            'daily': {'hour': 8, 'minute': 0},
            'weekly': {'hour': 8, 'minute': 0, 'day_of_week': 1},  # Monday
        }
    }
}
# SMS Configuration (Twilio)
TWILIO_ACCOUNT_SID = 'AC670c0b8f4d019125e428b8cca1d26cec'
TWILIO_AUTH_TOKEN = "2ced98ad055d4bc5605aa0a9d9eb98d7"
TWILIO_PHONE_NUMBER = "+19808426653"

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = 'hajjumrahservice072@gmail.com'
EMAIL_HOST_PASSWORD = 'pjrnsuqeoqnglohc'  

# File Upload Configuration
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024  # 5MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10MB

# AWS S3 Configuration (Optional)
USE_S3 = config('USE_S3', default=False, cast=bool)
if USE_S3:
    AWS_ACCESS_KEY_ID = config('AWS_ACCESS_KEY_ID')
    AWS_SECRET_ACCESS_KEY = config('AWS_SECRET_ACCESS_KEY')
    AWS_STORAGE_BUCKET_NAME = config('AWS_STORAGE_BUCKET_NAME')
    AWS_S3_REGION_NAME = config('AWS_S3_REGION_NAME', default='us-east-1')
    AWS_S3_CUSTOM_DOMAIN = f'{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com'
    AWS_DEFAULT_ACL = 'public-read'
    AWS_S3_OBJECT_PARAMETERS = {
        'CacheControl': 'max-age=86400',
    }
    DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
    STATICFILES_STORAGE = 'storages.backends.s3boto3.S3StaticStorage'

# Logging Configuration
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': BASE_DIR / 'logs' / 'django.log',
            'formatter': 'verbose',
        },
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'WARNING',
    },
    'loggers': {
        'django': {
            'handlers': ['file', 'console'],
            'level': 'INFO',
            'propagate': False,
        },
        'apps': {
            'handlers': ['file', 'console'],
            'level': 'DEBUG',
            'propagate': False,
        },
    },
}

# Security Settings
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
SECURE_HSTS_SECONDS = 31536000 if not DEBUG else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# JWT Configuration
JWT_SECRET_KEY = config('JWT_SECRET_KEY', default=SECRET_KEY)
JWT_ACCESS_TOKEN_LIFETIME = 60 * 60 * 24  # 1 day
JWT_REFRESH_TOKEN_LIFETIME = 60 * 60 * 24 * 7  # 7 days

# Rate Limiting
RATELIMIT_ENABLE = True
RATELIMIT_USE_CACHE = 'default'

# CKEditor 5 Configuration
DJANGO_CKEDITOR_5_CONFIGS = {
    'default': {
        'toolbar': [
            'heading', '|', 'bold', 'italic', 'link', 'bulletedList',
            'numberedList', 'blockQuote', 'imageUpload', 'insertTable',
            'mediaEmbed', 'undo', 'redo'
        ],
        'language': 'en',
    }
}
# Phone Number Configuration
PHONENUMBER_DEFAULT_REGION = 'IN'
PHONENUMBER_DEFAULT_FORMAT = 'NATIONAL'
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10MB
# Create logs directory if it doesn't exist
os.makedirs(BASE_DIR / 'logs', exist_ok=True)

