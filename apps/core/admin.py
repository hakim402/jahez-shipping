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
    return ["Foundation preview", "warning"]

def dashboard(request, context):
    context["preview_url"] = reverse("home")
    context["foundation_preview"] = True
    return context
