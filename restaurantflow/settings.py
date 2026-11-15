"""
RestaurantFlow Django Settings
Reads sensitive values from .env via python-decouple.
"""
from pathlib import Path
from datetime import timedelta

try:
    from decouple import config
except ImportError:
    def config(key, default=None, cast=str):
        import os
        val = os.environ.get(key, default)
        return cast(val) if val is not None else default

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config('SECRET_KEY', default='django-insecure-dev-only-change-me')
DEBUG = config('DEBUG', default=True, cast=bool)
ALLOWED_HOSTS = ['*']

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # third party
    'rest_framework',
    'rest_framework_simplejwt',
    'corsheaders',
    # local
    'accounts',
    'restaurant',
    'menu',
    'orders',
    'payments',
    'notifications',
    'kds',
    'checkout',
    'chef',
]

AUTH_USER_MODEL = 'accounts.User'

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'restaurantflow.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'restaurantflow.wsgi.application'

# --- Database ---
# SQLite for dev, swap to PostgreSQL for production using .env
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Uncomment below and fill .env for PostgreSQL:
# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.postgresql',
#         'NAME': config('DB_NAME'),
#         'USER': config('DB_USER'),
#         'PASSWORD': config('DB_PASSWORD'),
#         'HOST': config('DB_HOST', default='localhost'),
#         'PORT': config('DB_PORT', default='5432'),
#     }
# }

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Africa/Kampala'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# --- DRF ---
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 50,
}

# --- JWT ---
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=8),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
}

# --- CORS ---
# Dev: allow everything. Production: set CORS_ALLOWED_ORIGINS in .env
CORS_ALLOW_ALL_ORIGINS = DEBUG

# --- Celery ---
_redis = config('REDIS_URL', default='redis://localhost:6379/0')
CELERY_BROKER_URL = _redis
CELERY_RESULT_BACKEND = _redis
CELERY_TIMEZONE = TIME_ZONE

# --- FCM (Firebase Cloud Messaging for push notifications) ---
FCM_CREDENTIALS_PATH = config('FCM_CREDENTIALS_PATH', default=None)

# --- Flutterwave (mobile money) ---
FLUTTERWAVE_SECRET_KEY = config('FLUTTERWAVE_SECRET_KEY', default='')
FLUTTERWAVE_PUBLIC_KEY = config('FLUTTERWAVE_PUBLIC_KEY', default='')
FLUTTERWAVE_WEBHOOK_HASH = config('FLUTTERWAVE_WEBHOOK_HASH', default='')

# --- Yo! Payments (mobile money) ---
YO_PAYMENTS_API_USERNAME = config('YO_PAYMENTS_API_USERNAME', default='')
YO_PAYMENTS_API_PASSWORD = config('YO_PAYMENTS_API_PASSWORD', default='')
YO_PAYMENTS_USE_PRODUCTION = config('YO_PAYMENTS_USE_PRODUCTION', default=False, cast=bool)

# --- MTN MoMo (mobile money — direct, no aggregator) ---
MTN_MOMO_SUBSCRIPTION_KEY = config('MTN_MOMO_SUBSCRIPTION_KEY', default='')
MTN_MOMO_API_USER = config('MTN_MOMO_API_USER', default='')       # from provision_mtn_momo
MTN_MOMO_API_KEY = config('MTN_MOMO_API_KEY', default='')          # from provision_mtn_momo
MTN_MOMO_ENV = config('MTN_MOMO_ENV', default='sandbox')           # 'sandbox' or 'production'
MTN_MOMO_CURRENCY = config('MTN_MOMO_CURRENCY', default='EUR')     # sandbox ONLY accepts EUR
MTN_MOMO_CALLBACK_HOST = config('MTN_MOMO_CALLBACK_HOST', default='')
MTN_MOMO_PRODUCTION_BASE_URL = config('MTN_MOMO_PRODUCTION_BASE_URL', default='')  # MTN gives you this at Go-Live

# Which provider checkout/views.py actually calls — see payments/mobile_money.py
MOBILE_MONEY_PROVIDER = config('MOBILE_MONEY_PROVIDER', default='yo_payments')
