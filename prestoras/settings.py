"""
Django settings for prestoras project.
Sistema de Gestión de Préstamos Multiempresa
"""
import os
from datetime import timedelta
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-t3j@z=b0@+upo2encm1ojjtd&*ht5l*l+xo%2t*uj@komp%(!3')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get('DEBUG', 'True') == 'True'

ALLOWED_HOSTS = ['*']  # 🔴 PRODUCCIÓN: Configurar hosts específicos

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # Third party apps
    'corsheaders',
    
    # Local apps
    'apps.users',
    'apps.companies',
    'apps.zones',
    'apps.clients',
    'apps.loans',
    'apps.payments',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'prestoras.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
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

WSGI_APPLICATION = 'prestoras.wsgi.application'

# Database - PostgreSQL
DATABASES = {
    'default': {
        'ENGINE': 'django.contrib.gis.db.backends.postgis' if os.environ.get('USE_POSTGIS') == 'True' else 'django.db.backends.postgresql',
        'NAME': os.environ.get('DB_NAME', 'prestora'),
        'USER': os.environ.get('DB_USER', 'italo'),
        'PASSWORD': os.environ.get('DB_PASSWORD', 'italo2025.*/'),
        'HOST': os.environ.get('DB_HOST', 'localhost'),
        'PORT': os.environ.get('DB_PORT', '5432'),
        'OPTIONS': {
                    'client_encoding': 'UTF8',
                },
        'ATOMIC_REQUESTS': True,
        'CONN_MAX_AGE': 0,
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {
            'min_length': 8,
        }
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
LANGUAGE_CODE = 'es-pe'
TIME_ZONE = 'America/Lima'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
# STATIC_URL: URL base para servir archivos estáticos
# STATIC_URL = '/static/'
STATIC_URL = '/prestoras/static/'
# STATIC_ROOT: Directorio donde se recopilan archivos estáticos para producción
# Se usa con: python manage.py collectstatic
STATIC_ROOT = BASE_DIR / 'staticfiles'

# STATICFILES_DIRS: Directorios adicionales donde Django buscará archivos estáticos
# En desarrollo, Django busca archivos estáticos en cada app (app/static/)
# Para imágenes estáticas del sitio web, CSS, JS globales, etc.
STATICFILES_DIRS = [
    BASE_DIR / 'static',  # Carpeta global para archivos estáticos (imágenes web, CSS, JS)
]

# Media files (archivos subidos por usuarios: imágenes, documentos, etc.)
# MEDIA_URL: URL base para servir archivos media
# MEDIA_URL = '/media/'
MEDIA_URL = '/prestoras/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Custom User Model
AUTH_USER_MODEL = 'users.User'

# CORS Configuration
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:8000",
]

CORS_ALLOW_ALL_ORIGINS = DEBUG  # Solo en desarrollo

# JWT Configuration - Token de 24 horas
JWT_SECRET_KEY = SECRET_KEY
JWT_ALGORITHM = 'HS256'
JWT_EXPIRATION_DELTA = timedelta(hours=24)  # Token expira en 24 horas
JWT_REFRESH_EXPIRATION_DELTA = timedelta(days=7)

# Logging Configuration
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': BASE_DIR / 'logs' / 'django.log',
            'maxBytes': 1024 * 1024 * 5,  # 5MB
            'backupCount': 5,
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
        },
        'apps': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
    },
}

# Crear directorio de logs si no existe
os.makedirs(BASE_DIR / 'logs', exist_ok=True)
# Prefijo de URL para cuando corre bajo /prestoras/
# FORCE_SCRIPT_NAME = '/prestoras'
# USE_X_FORWARDED_HOST = True