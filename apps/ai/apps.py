from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class AIConfig(AppConfig):
    name = 'apps.ai'
    verbose_name = _('AI Workspace')
