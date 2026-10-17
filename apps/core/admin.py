from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin, GroupAdmin as BaseGroupAdmin
from django.contrib.auth.models import User, Group
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm

admin.site.index_title = _("Dashboard")


def navigation(request):
    def item(title, icon, url, permission=None):
        permissions = (permission,) if isinstance(permission, str) else permission
        return {"title": _(title), "icon": icon, "link": reverse(url),
                "permission": lambda request: not permissions or any(request.user.has_perm(p) for p in permissions)}
    return [{"title": _("Containers"), "items": [
        item("Containers", "inventory_2", "admin:containers_container_changelist", ("containers.view_container", "containers.change_container")),
        item("Dashboard", "dashboard", "admin:index"),
    ]}, {"title": _("Administration"), "collapsible": True, "items": [
        item("Users", "group", "admin:auth_user_changelist", ("auth.view_user", "auth.change_user")),
        item("Groups", "shield", "admin:auth_group_changelist", ("auth.view_group", "auth.change_group")),
    ]}]


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
    return [gettext("Local manual tracking") if settings.DEBUG else gettext("Manual tracking"), "warning"]


def dashboard(request, context):
    return context
