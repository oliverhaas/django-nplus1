from django.apps import AppConfig


class DjangoNPlus1Config(AppConfig):
    name = "django_nplus1"
    verbose_name = "Django N+1"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        from django_nplus1 import patch  # noqa: F401
