import os
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DJANGO_DEBUG=(bool, False),
    DJANGO_ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    STRIPE_PLATFORM_FEE_PERCENT=(int, 0),
)
environ.Env.read_env(BASE_DIR / ".env")

# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------
SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env("DJANGO_DEBUG")
ALLOWED_HOSTS = env("DJANGO_ALLOWED_HOSTS")
SOFT_LAUNCH = env.bool("SOFT_LAUNCH", default=False)

# Feature toggles — disable optional surfaces for deployments that don't
# need them. Apps stay in INSTALLED_APPS (migrations preserved); these
# flags only gate URL routing and template rendering.
FEATURE_COMMERCE = env.bool("FEATURE_COMMERCE", default=True)
FEATURE_COMMUNITY = env.bool("FEATURE_COMMUNITY", default=True)

# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------
INSTALLED_APPS = [
    # Wagtail (must come before django.contrib.admin)
    "wagtail.contrib.forms",
    "wagtail.contrib.redirects",
    "wagtail.embeds",
    "wagtail.sites",
    "wagtail.users",
    "wagtail.snippets",
    "wagtail.documents",
    "wagtail.images",
    "wagtail.search",
    "wagtail.admin",
    "wagtail",
    "wagtail.contrib.settings",
    "taggit",
    "modelcluster",
    # Django
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    "django.contrib.sitemaps",
    # Third-party
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "axes",
    "simple_history",
    "django_htmx",
    "easy_thumbnails",
    "django_q",
    # Project apps (core must come first for signals)
    "apps.core",
    "apps.creators",
    "apps.venues",
    "apps.events",
    "apps.commerce",
    "apps.community",
    "apps.pages",
]

if DEBUG:
    INSTALLED_APPS += [
        "debug_toolbar",
        "django_extensions",
    ]

SITE_ID = 1

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "apps.core.middleware.SuspensionMiddleware",
    "wagtail.contrib.redirects.middleware.RedirectMiddleware",
    # Captures request.user on every save so historical records know
    # who made the change.
    "simple_history.middleware.HistoryRequestMiddleware",
    # axes must come last so login attempts have already passed through
    # AuthenticationMiddleware and AccountMiddleware.
    "axes.middleware.AxesMiddleware",
]

if DEBUG:
    MIDDLEWARE.insert(2, "debug_toolbar.middleware.DebugToolbarMiddleware")
    INTERNAL_IPS = ["127.0.0.1"]

ROOT_URLCONF = "config.urls"

# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        # Explicit loader chain (rather than APP_DIRS=True) so the active
        # theme's templates/ directory can override anything by sitting at
        # the front. See apps.core.theming.ActiveThemeLoader.
        "OPTIONS": {
            "loaders": [
                "apps.core.theming.ActiveThemeLoader",
                "django.template.loaders.filesystem.Loader",
                "django.template.loaders.app_directories.Loader",
            ],
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "wagtail.contrib.settings.context_processors.settings",
                "apps.pages.context_processors.site_settings",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
DATABASES = {
    "default": env.db("DATABASE_URL", default="sqlite:///db.sqlite3"),
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Cache & Sessions
# ---------------------------------------------------------------------------
REDIS_URL = env("REDIS_URL", default="")
if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": REDIS_URL,
            "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
        }
    }
    SESSION_ENGINE = "django.contrib.sessions.backends.cache"
    SESSION_CACHE_ALIAS = "default"

# ---------------------------------------------------------------------------
# Authentication (django-allauth)
# ---------------------------------------------------------------------------
AUTHENTICATION_BACKENDS = [
    # axes' standalone backend only counts failures; the real auth is
    # still done by ModelBackend/allauth below.
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

# Brute-force lockout (django-axes): lock after 5 failures for the same
# (username, ip) pair, cooloff 30 minutes, reset counter on success.
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = 0.5  # hours
AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"]]
AXES_RESET_ON_SUCCESS = True
AXES_LOCKOUT_TEMPLATE = None  # 403 with default body; can be customized later
# Allauth posts the identifier as "login" (it accepts either email or
# username). Tell axes to pull the tracking key from that field.
AXES_USERNAME_FORM_FIELD = "login"
# New allauth settings format (v65+)
ACCOUNT_LOGIN_METHODS = {"email", "username"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "username*", "password1*", "password2*"]
ACCOUNT_EMAIL_VERIFICATION = "mandatory"
ACCOUNT_SIGNUP_REDIRECT_URL = "/welcome/"
LOGIN_REDIRECT_URL = "/"
ACCOUNT_LOGOUT_REDIRECT_URL = "/"
ACCOUNT_FORMS = {"signup": "apps.core.forms.TurnstileSignupForm"}

# ---------------------------------------------------------------------------
# Cloudflare Turnstile
# ---------------------------------------------------------------------------
TURNSTILE_SITE_KEY = env("TURNSTILE_SITE_KEY", default="")
TURNSTILE_SECRET_KEY = env("TURNSTILE_SECRET_KEY", default="")

# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------
# Use filebased backend in dev to avoid quoted-printable line wrapping
# that mangles confirmation URLs in the console backend.
# Emails are written to /tmp/oilregion-emails/ as plain text files.
# In production, use django.core.mail.backends.smtp.EmailBackend with
# your Modoboa SMTP credentials.
EMAIL_BACKEND = env(
    "EMAIL_BACKEND",
    default="django.core.mail.backends.filebased.EmailBackend" if DEBUG
    else "django.core.mail.backends.smtp.EmailBackend",
)
if EMAIL_BACKEND == "django.core.mail.backends.filebased.EmailBackend":
    EMAIL_FILE_PATH = BASE_DIR / "tmp_emails"
    EMAIL_FILE_PATH.mkdir(exist_ok=True)
EMAIL_HOST = env("EMAIL_HOST", default="localhost")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="noreply@oilregionindie.com")
SERVER_EMAIL = env("SERVER_EMAIL", default="errors@oilregionindie.com")

# Site admins — receive profile submission notifications and error emails
# Format: "Name:email,Name:email" e.g. "Jerome:jerome@oilregionindie.com"
_admins_raw = env.list("DJANGO_ADMINS", default=[])
ADMINS = [tuple(a.split(":")) for a in _admins_raw if ":" in a]

# ---------------------------------------------------------------------------
# Static & Media
# ---------------------------------------------------------------------------
STATIC_URL = "/static/"
# `themes/` is exposed at /static/themes/<name>/... so any theme's
# theme.css and assets are reachable regardless of which is active.
STATICFILES_DIRS = [
    BASE_DIR / "static",
    ("themes", BASE_DIR / "themes"),
]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# Default storage backends — overridden below when S3 is configured.
# In production (not DEBUG), use ManifestStaticFilesStorage so each
# collectstatic run rewrites filenames with a content hash. Without
# this, deploys that change CSS/JS may serve stale assets to repeat
# visitors despite long Cache-Control headers.
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage" if DEBUG
            else "django.contrib.staticfiles.storage.ManifestStaticFilesStorage"
        ),
    },
}

# S3-compatible storage (production)
if env("AWS_STORAGE_BUCKET_NAME", default=""):
    STORAGES["default"]["BACKEND"] = "storages.backends.s3boto3.S3Boto3Storage"
    AWS_ACCESS_KEY_ID = env("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = env("AWS_SECRET_ACCESS_KEY")
    AWS_STORAGE_BUCKET_NAME = env("AWS_STORAGE_BUCKET_NAME")
    AWS_S3_ENDPOINT_URL = env("AWS_S3_ENDPOINT_URL", default="")
    AWS_S3_REGION_NAME = env("AWS_S3_REGION_NAME", default="us-east-1")
    AWS_QUERYSTRING_AUTH = False
    AWS_DEFAULT_ACL = "public-read"

# ---------------------------------------------------------------------------
# Stripe
# ---------------------------------------------------------------------------
STRIPE_PUBLIC_KEY = env("STRIPE_PUBLIC_KEY", default="")
STRIPE_SECRET_KEY = env("STRIPE_SECRET_KEY", default="")
STRIPE_WEBHOOK_SECRET = env("STRIPE_WEBHOOK_SECRET", default="")
STRIPE_PLATFORM_FEE_PERCENT = env("STRIPE_PLATFORM_FEE_PERCENT")

# ---------------------------------------------------------------------------
# Wagtail
# ---------------------------------------------------------------------------
WAGTAIL_SITE_NAME = env("WAGTAIL_SITE_NAME", default="Oil Region Creative Hub")
WAGTAILADMIN_BASE_URL = env("WAGTAILADMIN_BASE_URL", default="http://localhost:8000")
WAGTAILSEARCH_BACKENDS = {
    "default": {
        "BACKEND": "wagtail.search.backends.database",
    }
}
WAGTAILIMAGES_MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10MB

# ---------------------------------------------------------------------------
# Django-Q2 (task queue)
# ---------------------------------------------------------------------------
Q_CLUSTER = {
    # Name is the per-instance cluster identifier in Django Q's DB.
    # When two hubs share a Postgres cluster (as they will on omwom),
    # this MUST be unique per instance or workers will steal each
    # other's scheduled tasks. The wizard / Ansible playbook should
    # set this to the deployer's hub name; defaults to "oilregion".
    "name": env("Q_CLUSTER_NAME", default="oilregion"),
    "workers": 2,
    "recycle": 500,
    "timeout": 60,
    "compress": True,
    "save_limit": 250,
    "queue_limit": 500,
    "cpu_affinity": 1,
    "label": "Django Q",
    "orm": "default",
}
if REDIS_URL:
    Q_CLUSTER.update(
        {
            "redis": REDIS_URL,
            "orm": None,
        }
    )

# ---------------------------------------------------------------------------
# Thumbnails
# ---------------------------------------------------------------------------
THUMBNAIL_ALIASES = {
    "": {
        "avatar": {"size": (300, 300), "crop": True},
        "card": {"size": (400, 300), "crop": True},
        "header": {"size": (1200, 400), "crop": True},
        "product": {"size": (600, 600), "crop": True},
    },
}

# ---------------------------------------------------------------------------
# Security (production overrides)
# ---------------------------------------------------------------------------
if not DEBUG:
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "apps": {"handlers": ["console"], "level": "DEBUG" if DEBUG else "INFO"},
    },
}

# ---------------------------------------------------------------------------
# Error monitoring (Sentry)
#
# Activated only when SENTRY_DSN is set in .env. Without a DSN, sentry_sdk
# is initialised with empty arguments and is a no-op — safe to keep the
# import unconditional. Add your DSN at https://sentry.io/ (or GlitchTip
# self-hosted) and paste it into .env to start receiving error reports.
# ---------------------------------------------------------------------------
SENTRY_DSN = env("SENTRY_DSN", default="")
if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration()],
        # Performance monitoring sample rate. Soft-launch default of 0.1
        # means 10 % of requests are traced — plenty of signal without
        # filling the free-tier quota.
        traces_sample_rate=env.float("SENTRY_TRACES_SAMPLE_RATE", default=0.1),
        # Send the user.id only — never PII like email or username.
        send_default_pii=False,
        environment=env("SENTRY_ENVIRONMENT", default="production" if not DEBUG else "development"),
        release=env("SENTRY_RELEASE", default=""),
    )
