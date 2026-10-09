from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin, GroupAdmin as BaseGroupAdmin
from django.contrib.auth.models import User, Group
from django.urls import reverse
from unfold.admin import ModelAdmin
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm

admin.site.unregister(User)
admin.site.unregister(Group)
@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):
    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm
@admin.register(Group)
class GroupAdmin(BaseGroupAdmin, ModelAdmin):
    pass

def environment(request):
    from django.conf import settings
    from django.utils.translation import gettext
    return [gettext("Local operations") if settings.DEBUG else gettext("Operations"), "warning" if settings.DEBUG else "success"]

def dashboard(request, context):
    from django.conf import settings
    from django.db.models import Q
    from apps.shipments.models import Status
    from apps.shipments.services import active_shipments, delayed_q, TERMINAL
    context["preview_url"] = reverse("home")
    context["business_timezone"] = settings.BUSINESS_TIME_ZONE
    from apps.tracking.adapter import configuration
    context["carrier_config"] = configuration()
    context["can_view_integrations"] = request.user.has_perm("tracking.view_integrationjob")
    context["can_view_shipments"] = request.user.has_perm("shipments.view_shipment")
    context["can_add_shipment"] = request.user.has_perm("shipments.add_shipment")
    if context["can_view_shipments"]:
        shipments = active_shipments()
        attention = shipments.exclude(status__in=TERMINAL).filter(delayed_q() | Q(status=Status.HOLD))
        context["metrics"] = {
            "pending": shipments.filter(status__in=[Status.CREATED, Status.WAREHOUSE, Status.PREPARING]).count(),
            "transit": shipments.filter(status__in=[Status.DEPARTED, Status.TRANSIT, Status.CUSTOMS, Status.ARRIVED, Status.OUT]).count(),
            "delivered": shipments.filter(status=Status.DELIVERED).count(),
            "attention": attention.count(),
        }
        context["recent_shipments"] = shipments.select_related("customer").order_by("-updated_at")[:6]
        context["attention_shipments"] = attention[:5]
    return context
