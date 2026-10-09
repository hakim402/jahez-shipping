from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ShipmentsConfig(AppConfig):
    name = "apps.shipments"
    verbose_name = _("Shipping operations")
