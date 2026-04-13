from django.apps import AppConfig


class DjangoNPlus1Config(AppConfig):
    name = "django_nplus1"
    verbose_name = "Django N+1"

    def ready(self) -> None:
        from django.conf import settings

        from django_nplus1 import patch  # noqa: F401

        if getattr(settings, "NPLUS1_CELERY", False):
            from django_nplus1.celery import setup_celery_detection

            setup_celery_detection()
