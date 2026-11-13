"""
Production settings for certificate_project project.
"""

from .settings import *
import os

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get('SECRET_KEY')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False

# Production allowed hosts
# Production allowed hosts
# ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', 'verify.cscindia.org.in,offerletters.cscindia.org.in,www.offerletters.cscindia.org.in').split(',')
ALLOWED_HOSTS = [
    'offerletters.cscindia.org.in',
    'www.offerletters.cscindia.org.in',
    'verify.cscindia.org.in',
    '209.182.233.125',
    '127.0.0.1',
    'localhost',
]

CSRF_TRUSTED_ORIGINS = [
    'https://offerletters.cscindia.org.in',
    'https://www.offerletters.cscindia.org.in',
]

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# Production database (PostgreSQL)
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('DB_NAME'),
        'USER': os.environ.get('DB_USER'),
        'PASSWORD': os.environ.get('DB_PASSWORD'),
        'HOST': os.environ.get('DB_HOST'),
        'PORT': os.environ.get('DB_PORT', '5432'),
    }
}

# Security settings for production
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Session and CSRF security
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True

# Static files configuration for production
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# Email configuration for production
EMAIL_HOST = os.environ.get('EMAIL_HOST')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', 587))
EMAIL_USE_TLS = os.environ.get('EMAIL_USE_TLS', 'True').lower() == 'true'
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD')
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL')

# Google Drive API configuration
GOOGLE_DRIVE_CREDENTIALS_FILE = os.environ.get('GOOGLE_DRIVE_CREDENTIALS_FILE')
GOOGLE_DRIVE_FOLDER_ID = os.environ.get('GOOGLE_DRIVE_FOLDER_ID')

# Site configuration
SITE_DOMAIN = os.environ.get('SITE_DOMAIN', 'offerletters.cscindia.org.in')
SITE_PROTOCOL = os.environ.get('SITE_PROTOCOL', 'https')
BASE_URL = os.environ.get('BASE_URL', 'https://offerletters.cscindia.org.in')

# CSRF trusted origins for production
CSRF_TRUSTED_ORIGINS = [
    "https://offerletters.cscindia.org.in",
    "http://offerletters.cscindia.org.in",
]
