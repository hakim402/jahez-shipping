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
        return {"title": _(title), "icon": icon, "link": reverse(url),
                "permission": lambda request: not permission or request.user.has_perm(permission)}
    return [{"title": _("Administration"), "items": [
        item("Dashboard", "dashboard", "admin:index"),
        item("Users", "group", "admin:auth_user_changelist", "auth.view_user"),
        item("Groups", "shield", "admin:auth_group_changelist", "auth.view_group"),
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
    return [gettext("Local preparation") if settings.DEBUG else gettext("Preparation"), "warning"]


def dashboard(request, context):
    return context
