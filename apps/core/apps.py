from django.apps import AppConfig
class CoreConfig(AppConfig):
    name = "apps.core"
    def ready(self):
        from django.conf import settings
        settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
        settings.PRIVATE_ROOT.mkdir(parents=True, exist_ok=True)
