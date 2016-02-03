"""
Django settings for geo_django project.

Generated by 'django-admin startproject' using Django 1.8.5.

For more information on this file, see
https://docs.djangoproject.com/en/1.8/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/1.8/ref/settings/
"""

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_PATH = BASE_DIR

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/1.8/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'lcw5&qk37g!f0j^-_r1999&)ijb4dg6(d&l4--!%ufvtj++^-b'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = []


# Application definition

INSTALLED_APPS = (
    'django.contrib.admin',         # basic django admin functionalities
    'django.contrib.auth',          # core authentication system
    'django.contrib.sites',         # site mgmt
    'django.contrib.contenttypes',  # allows to associate permissions with models
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',   # django staticfiles-finder
    'django.contrib.gis',           # geo-django extension
    'django_jasmine',               # used for running jasmine-tests against the js-sources
    'crow',                         # OeQ-extension
    'ates',                         # Models for ATES-BuildingDB
    'django_extensions',            # Enhanced commandline-tools for generating database-visualisations
    'registration',                 # Django Redux for user registration
    'bootstrap3',                   # Enables easier usage of bootstrap tags in django templates
)

JASMINE_TEST_DIRECTORY = os.path.join(BASE_DIR, 'crow', 'jasmine')

MIDDLEWARE_CLASSES = (
    'django.contrib.sessions.middleware.SessionMiddleware',             # Handle sessions across requests
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',          # Associate users with requests during sessions
    'django.contrib.auth.middleware.SessionAuthenticationMiddleware',   # Logs out user after password change
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django.middleware.security.SecurityMiddleware',
)

ROOT_URLCONF = 'crow_django.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')]
        ,
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

WSGI_APPLICATION = 'crow_django.wsgi.application'


# Database
# https://docs.djangoproject.com/en/1.8/ref/settings/#databases
DATABASES = {
    'default': {
        'ENGINE': 'django.contrib.gis.db.backends.postgis',
        'NAME': 'crow_django',
        'USER': 'djangocrow',
        'PASSWORD': 'djangocrow'
    },
    'atesdb': {
        'ENGINE': 'django.contrib.gis.db.backends.postgis',
        'NAME': 'buildingDB',
        'USER': 'ATESuser',
        'PASSWORD': 'ATESuser',
    }
}
DATABASE_ROUTERS = ['ates.routers.AtesRouter']

AUTHENTICATION_BACKENDS = (
    # Needed to login by username in Django admin, regardless of `allauth`
    'django.contrib.auth.backends.ModelBackend',
)

LOGIN_REDIRECT_URL = '/'
ACCOUNT_ACTIVATION_DAYS = 7
REGISTRATION_EMAIL_HTML = True

EMAIL_BACKEND = 'django.core.mail.backends.filebased.EmailBackend'
EMAIL_FILE_PATH = os.path.join(BASE_DIR, 'app-messages')

SITE_ID = 1

# Internationalization
# https://docs.djangoproject.com/en/1.8/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_L10N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/1.8/howto/static-files/

STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, '..', 'crow')
