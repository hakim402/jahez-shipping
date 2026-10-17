from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.shortcuts import redirect
from django.contrib import messages
from .refresh import refresh_container
from django.db.models import F
from django.template.loader import render_to_string
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import get_language, gettext_lazy as _, gettext
from unfold.admin import ModelAdmin, StackedInline

from .forms import ContainerForm, ManualEventForm, ManualEventFormSet
from .models import Container, ContainerEvent
from .values import Status
from .tracking import active_journeys, attention_query, attention_text


def time_context(value):
    if not isinstance(value, dict) or not value.get("raw"):
        return None
    return {"raw": value["raw"], "designation": gettext("Actual") if value["designation"] == "actual" else gettext("Estimated"),
            "precision": gettext("Date only") if value["precision"] == "date" else "",
            "zone": value.get("source_timezone") or gettext("Timezone not supplied")}


class ArchiveFilter(admin.SimpleListFilter):
    title = _("Archive state")
    parameter_name = "archive"

    def lookups(self, request, model_admin):
        return [("active", _("Active")), ("archived", _("Archived"))]

    def queryset(self, request, queryset):
        if self.value() == "active":
            return queryset.filter(archived_at__isnull=True)
        if self.value() == "archived":
            return queryset.filter(archived_at__isnull=False)
        return queryset


class ManualEventInline(StackedInline):
    model = ContainerEvent
    form = ManualEventForm
    formset = ManualEventFormSet
    extra = 0
    max_num = 50
    can_delete = False
    verbose_name = _("Manual update")
    verbose_name_plural = _("Manual timeline updates")
    fields = [("title_en", "title_ar"), ("detail_en", "detail_ar"), "location", "designation", "source_time", "is_public"]

    def get_queryset(self, request):
        return super().get_queryset(request).filter(origin="manual").order_by(F("source_time__raw").asc(nulls_last=True), "pk")

    def has_add_permission(self, request, obj=None):
        return request.user.has_perm("containers.add_containerevent") and request.user.has_perm("containers.change_container")

    def has_change_permission(self, request, obj=None):
        return request.user.has_perm("containers.change_containerevent") and request.user.has_perm("containers.change_container")


class AttentionFilter(admin.SimpleListFilter):
    title = _("Refresh attention")
    parameter_name = "attention"

    def lookups(self, request, model_admin):
        return [("needed", _("Needs attention")), ("current", _("Up to date"))]

    def queryset(self, request, queryset):
        if self.value() == "needed":
            return active_journeys(queryset).filter(attention_query())
        if self.value() == "current":
            return active_journeys(queryset).exclude(attention_query())
        return queryset


@admin.register(Container)
class ContainerAdmin(ModelAdmin):
    form = ContainerForm
    change_form_template = "admin/containers/change_form.html"
    inlines = [ManualEventInline]
    list_display = ["identity", "route", "status", "eta", "last_refresh_success_at", "refresh_attention", "publication_state"]
    list_filter = [ArchiveFilter, AttentionFilter, "is_published"]
    search_fields = ["container_number", "search_reference", "lookup_code", "vessel", "voyage", "origin_label_en", "origin_label_ar", "destination_label_en", "destination_label_ar"]
    search_help_text = _("Search by container, B/L, JAHEZ code or vessel.")
    list_per_page = 25
    actions = None
    readonly_fields = ["status", "timeline", "refresh_capability", "refresh_attention", "tracking_links", "bound_search_reference", "bound_container_number",
                       "source_adapter", "source_website", "raw_status", "carrier_status", "last_refresh_attempt_at", "last_refresh_success_at", "last_failure_code"]

    def get_urls(self):
        return [path("<int:object_id>/refresh/", self.admin_site.admin_view(self.refresh_view), name="containers_container_refresh")] + super().get_urls()

    def refresh_view(self, request, object_id):
        obj = self.get_object(request, str(object_id))
        if obj is None:
            raise Http404
        if not self.has_change_permission(request, obj):
            raise PermissionDenied
        if request.method not in ("GET", "POST"):
            from django.http import HttpResponseNotAllowed
            return HttpResponseNotAllowed(["GET", "POST"])
        if request.method == "POST":
            result = refresh_container(obj.pk)
            if result.ok:
                text = gettext("Carrier check completed. Review saved facts and the public snapshot before sharing.")
                if result.code == "unknown_status":
                    text = gettext("Carrier check completed. Some stages need review; no completion was inferred.")
                messages.add_message(request, messages.WARNING if result.code == "unknown_status" else messages.SUCCESS, text)
            else:
                errors = {
                    "ambiguous_container": gettext("Several containers were found. Verify and select the physical container before retrying."),
                    "identity_mismatch": gettext("Source identity or route did not match. Verify the registered journey; saved facts were kept."),
                    "concurrent_change": gettext("The journey changed or another refresh is running. Reload and try again; saved facts were kept."),
                    "ai_unavailable": gettext("Label translation is unavailable. Check the configured Groq service and try again; saved facts were kept."),
                    "timeout": gettext("The carrier check timed out. Try again later or use verified manual updates; saved facts were kept."),
                }
                messages.error(request, errors.get(result.code, gettext("The carrier check could not be accepted. Check the source or use verified manual updates; saved facts were kept.")))
            return redirect(reverse("admin:containers_container_change", args=[obj.pk]))
        return TemplateResponse(request, "admin/containers/refresh.html", {
            **self.admin_site.each_context(request), "opts": self.model._meta, "original": obj,
            "title": _("Refresh now"), "can_refresh": not obj.archived_at,
        })

    class Media:
        css = {"all": ["css/containers-admin.css"]}
        js = ["js/containers-admin.js"]

    def get_fieldsets(self, request, obj=None):
        editable = self.has_change_permission(request, obj) if obj else self.has_add_permission(request)
        bound = bool(obj and obj.container_number)
        identity = ["bound_search_reference", "bound_container_number"] if bound else ["search_reference", "container_number"]
        if editable and not bound:
            identity.append("confirm_identity")
        publication = ["is_published", "auto_publish_carrier_updates", "is_archived" if editable else "publication_state"]
        if editable:
            publication.append("confirm_publication")
        publication.append("tracking_links")
        return [
            (_("Basic details"), {"fields": identity + [("equipment_type", "equipment_quantity"), ("origin_code", "destination_code"),
                ("origin_label_en", "origin_label_ar"), ("destination_label_en", "destination_label_ar"), ("vessel", "voyage")]}),
            (_("Progress and timeline"), {"fields": ["status", "manual_status_override", "manual_notes_en", "manual_notes_ar", "timeline",
                ("last_refresh_attempt_at", "last_refresh_success_at"), "refresh_attention", "refresh_capability"]}),
            (_("Publication"), {"fields": publication, "description": _("Customers see the last reviewed public snapshot. Confirm publication changes after reviewing facts and timeline updates.")}),
            (_("Source and advanced details"), {"classes": ["collapse"], "description": _("Manual-copy fallback: enter only carrier facts you have checked. Leave missing facts empty."),
                "fields": ["source_adapter", "source_website", "raw_status", "carrier_status", "departure_actual", "departure_estimated", "arrival_actual", "arrival_estimated",
                           "last_failure_code"]}),
        ]

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if "expected_revision" not in form.base_fields:
            from django import forms
            form.base_fields["expected_revision"] = forms.IntegerField(widget=forms.HiddenInput, required=False)
        return form

    def get_readonly_fields(self, request, obj=None):
        fields = list(self.readonly_fields)
        if obj and obj.container_number:
            fields += ["search_reference", "container_number"]
        if not self.has_change_permission(request, obj) and obj:
            fields.append("publication_state")
        return fields

    def get_formset_kwargs(self, request, obj, inline, prefix):
        values = super().get_formset_kwargs(request, obj, inline, prefix)
        values["form_kwargs"] = {"request": request}
        return values

    def has_delete_permission(self, request, obj=None):
        return False

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for instance in instances:
            if instance.pk:
                stored = ContainerEvent.objects.get(pk=instance.pk)
                if stored.container_id != form.instance.pk or stored.origin != "manual":
                    raise PermissionDenied
            instance.origin = "manual"
            instance.container = form.instance
            instance.save()
            # Keep Django's ordinary admin log; no extra business audit table.
        formset.save_m2m()

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        if form.cleaned_data.get("confirm_publication"):
            from .publication import publish_reviewed
            publish_reviewed(form.instance)
        elif not form.instance.is_published and form.instance.public_snapshot:
            form.instance.public_snapshot = {}
            form.instance.save(update_fields=["public_snapshot"])
        else:
            from .publication import withdraw_manual_events
            withdraw_manual_events(form.instance)

    @admin.display(description=_("Container / B/L"))
    def identity(self, obj):
        return format_html('<bdi dir="ltr">{}</bdi><br><small><bdi dir="ltr">{}</bdi></small>', obj.container_number or gettext("Not selected"), obj.search_reference)

    @admin.display(description=_("Route"))
    def route(self, obj):
        return format_html('<bdi dir="ltr">{} → {}</bdi>', obj.origin_code or "—", obj.destination_code or "—")

    @admin.display(description=_("Display status"))
    def status(self, obj):
        return str(Status(obj.display_status).label) if obj else str(Status.UNKNOWN.label)

    @admin.display(description=_("Arrival"))
    def eta(self, obj):
        value = time_context(obj.arrival_actual or obj.arrival_estimated)
        if not value:
            return gettext("Not provided")
        return format_html('{} <bdi dir="ltr">{}</bdi><br><small>{} · {}</small>', value["designation"], value["raw"], value["precision"], value["zone"])

    @admin.display(description=_("Publication / archive"))
    def publication_state(self, obj):
        return " · ".join([gettext("Published") if obj.is_published else gettext("Private"), gettext("Archived") if obj.archived_at else gettext("Active")])

    @admin.display(description=_("Refresh attention"))
    def refresh_attention(self, obj):
        return attention_text(obj)

    @admin.display(description=_("B/L or search reference"))
    def bound_search_reference(self, obj):
        return format_html('<bdi dir="ltr">{}</bdi>', obj.search_reference)

    @admin.display(description=_("Container number"))
    def bound_container_number(self, obj):
        return format_html('<bdi dir="ltr">{}</bdi><p class="help">{}</p>', obj.container_number,
            gettext("This journey is bound. Register a separate journey to use another source identity."))

    @admin.display(description=_("Refresh capability"))
    def refresh_capability(self, obj):
        if not obj or not obj.pk:
            return gettext("Save the journey before checking the carrier.")
        if obj.archived_at:
            return gettext("Archived journeys cannot be refreshed. Restore the journey deliberately before checking.")
        return gettext("Use Refresh now to check the saved journey. Save manual edits first. Public updates follow the reviewed publication settings.")

    @admin.display(description=_("Tracking link"))
    def tracking_links(self, obj):
        if not obj or not obj.pk:
            return gettext("Save the journey to generate its shared JAHEZ code.")
        context = {"code": obj.lookup_code, "path": obj.tracking_path("ar" if get_language() == "ar" else "en"),
                   "can_copy": obj.is_published and not obj.archived_at and bool(obj.public_snapshot)}
        return mark_safe(render_to_string("admin/containers/tracking_link.html", context))

    @admin.display(description=_("Saved timeline"))
    def timeline(self, obj):
        if not obj or not obj.pk:
            return gettext("Save the journey before adding timeline updates.")
        events = list(obj.events.order_by(F("source_time__raw").asc(nulls_last=True), "pk")[:201])
        arabic = get_language() == "ar"
        rows = [{"title": (event.title_ar or event.title_en) if arabic else (event.title_en or event.title_ar),
                 "detail": (event.detail_ar or event.detail_en) if arabic else (event.detail_en or event.detail_ar),
                 "origin": event.get_origin_display(), "location": event.location or event.location_code,
                 "time": time_context(event.source_time), "public": event.is_public} for event in events[:200]]
        return mark_safe(render_to_string("admin/containers/timeline.html", {"rows": rows, "limited": len(events) > 200}))
