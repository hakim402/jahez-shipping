from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin, GroupAdmin as BaseGroupAdmin
from django.contrib.auth.models import User, Group
from django.urls import reverse
from unfold.admin import ModelAdmin
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm
from django.utils.translation import gettext_lazy as _

admin.site.index_title = _("Dashboard")


def navigation(request):
    def item(title, icon, url, *permissions):
        return {"title": _(title), "icon": icon, "link": reverse(url),
                "permission": lambda request: all(request.user.has_perm(p) for p in permissions)}
    return [
        {"title": _("Daily work"), "items": [
            item("Dashboard", "dashboard", "admin:index"),
            item("Shipments", "package_2", "admin:shipments_shipment_changelist", "shipments.view_shipment"),
            item("Customers", "group", "admin:shipments_customer_changelist", "shipments.view_customer"),
            item("Private documents", "description", "admin:shipments_document_changelist", "shipments.view_document"),
        ]},
        {"title": _("Tools"), "items": [
            item("Operational assistant", "manage_search", "admin:ai_assistant", "ai.query_shipments", "shipments.view_shipment"),
            item("AI Workspace", "auto_awesome", "admin:ai_workspace", "ai.view_aidraft"),
            item("Integration health", "monitor_heart", "admin:integration_health", "tracking.view_integrationjob", "shipments.view_shipment"),
        ]},
        {"title": _("Administration"), "collapsible": True, "items": [
            item("Audit history", "history", "admin:shipments_auditentry_changelist", "shipments.view_auditentry"),
            item("Integration jobs", "work_history", "admin:tracking_integrationjob_changelist", "tracking.view_integrationjob", "shipments.view_shipment"),
            item("Webhook receipts", "inbox", "admin:tracking_webhookreceipt_changelist", "tracking.view_webhookreceipt"),
            item("Users", "group", "admin:auth_user_changelist", "auth.view_user"),
            item("Groups", "shield", "admin:auth_group_changelist", "auth.view_group"),
        ]},
    ]

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
    context["business_timezone"] = settings.BUSINESS_TIME_ZONE
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
