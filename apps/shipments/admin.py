from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import FileResponse, Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin, TabularInline
from .forms import ShipmentForm, EventForm, DocumentUploadForm
from .models import Customer, Shipment, ShipmentItem, TrackingLeg, TrackingEvent, Document, AuditEntry
from .services import audit, snapshot, save_shipment, save_child, require, archive_shipment, rotate_shipment_reference
from .uploads import store_document


class RetainedAdmin(ModelAdmin):
    """Retain operational records and immutable audit history; archive shipments."""
    actions = None
    list_per_page = 25
    warn_unsaved_form = True

    def has_delete_permission(self, request, obj=None):
        return False


class ItemInline(TabularInline):
    model = ShipmentItem
    extra = 0
    can_delete = False
    fields = ("description_en", "description_ar", "quantity", "unit", "unit_ar", "cartons", "public")


class LegInline(TabularInline):
    model = TrackingLeg
    extra = 0
    can_delete = False
    fields = ("sequence", "label", "carrier_identifier", "tracking_number", "registration_state")
    readonly_fields = ("registration_state",)


class EventInline(TabularInline):
    model = TrackingEvent
    form = EventForm
    extra = 0
    can_delete = False
    fields = ("occurred_at", "title_en", "title_ar", "body_en", "body_ar", "mapped_status", "public")


@admin.register(Shipment)
class ShipmentAdmin(RetainedAdmin):
    form = ShipmentForm
    list_display = ("id", "customer", "internal_order", "status_badge", "mode", "publication", "eta", "updated_at")
    list_filter = ("status", "mode", "tracking_mode", "published", "is_demo", "archived_at")
    search_fields = ("internal_order", "bill_number", "customer__name", "customer__company")
    list_select_related = ("customer",)
    readonly_fields = ("status_badge", "created_at", "updated_at", "archived_at", "operational_links", "reference_display")
    inlines = (ItemInline, LegInline, EventInline)
    change_form_template = "admin/shipments/shipment_change.html"
    fieldsets = (
        (_("Shipment overview"), {"fields": ("customer", "internal_order", "bill_number", "mode", "tracking_mode", "status", "status_badge")}),
        (_("Approved public route and dates"), {"fields": (("origin_en", "origin_ar"), ("destination_en", "destination_ar"), "eta", "actual_arrival", "delivered_at", "published")}),
        (_("Status control"), {"fields": ("confirmed_delay", "delay_reason", "status_locked", "override_reason", "correction_reason", "confirm_complete_shipment")}),
        (_("Private access and records"), {"fields": ("reference_display", "internal_notes", "operational_links", "archived_at", "created_at", "updated_at", "revision_token")}),
    )

    def get_form(self, request, obj=None, **kwargs):
        base = super().get_form(request, obj, **kwargs)
        class RequestForm(base):
            def __init__(self, *args, **kw):
                kw["user"] = request.user
                super().__init__(*args, **kw)
        return RequestForm

    def get_readonly_fields(self, request, obj=None):
        fields = list(super().get_readonly_fields(request, obj))
        if not request.user.has_perm("shipments.publish_shipment"):
            fields += ["published"]
        if not request.user.has_perm("shipments.correct_status"):
            fields += ["status_locked", "override_reason"]
        return fields

    def reference_display(self, obj):
        return format_html('<code dir="ltr" class="jahez-reference">{}</code>', obj.reference)
    reference_display.short_description = _("Private JAHEZ reference")

    @admin.display(description=_("Status"))
    def status_badge(self, obj):
        return format_html('<span class="jahez-status">{}</span>', obj.get_status_display())

    @admin.display(description=_("Publication"))
    def publication(self, obj):
        return _("Archived") if obj.archived_at else _("Published") if obj.published else _("Private draft")

    def operational_links(self, obj):
        if not obj.pk:
            return _("Save the shipment first, then add products, timeline and private documents.")
        return format_html('<a href="{}?shipment__id__exact={}">{}</a> · <a href="{}?shipment__id__exact={}">{}</a>',
            reverse("admin:shipments_document_changelist"), obj.pk, _("Private documents"),
            reverse("admin:shipments_auditentry_changelist"), obj.pk, _("Audit history"))
    operational_links.short_description = _("Related records")

    def has_change_permission(self, request, obj=None):
        return super().has_change_permission(request, obj) and not (obj and obj.archived_at)

    def save_model(self, request, obj, form, change):
        save_shipment(obj, request.user, form.cleaned_data.get("revision_token"), form.changed_data, form.cleaned_data.get("correction_reason", ""), confirm_complete_shipment=form.cleaned_data.get("confirm_complete_shipment", False))

    def save_formset(self, request, form, formset, change):
        for instance in formset.save(commit=False):
            save_child(instance, request.user, fields=["inline_saved"])
        formset.save_m2m()

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        extra = extra_context or {}
        extra.update(can_archive=request.user.has_perm("shipments.archive_shipment"), can_rotate=request.user.has_perm("shipments.rotate_reference"))
        # Validation catches normal stale forms; catch a race after validation too.
        try:
            return super().changeform_view(request, object_id, form_url, extra)
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
            return HttpResponseRedirect(request.path)

    def get_urls(self):
        return [path("<int:pk>/control/", self.admin_site.admin_view(self.control), name="shipments_shipment_control")] + super().get_urls()

    def control(self, request, pk):
        obj = get_object_or_404(Shipment, pk=pk)
        action = request.POST.get("action") or request.GET.get("action")
        permissions = {"archive": "archive_shipment", "restore": "archive_shipment", "rotate": "rotate_reference"}
        if action not in permissions:
            raise Http404
        require(request.user, permissions[action])
        if request.method == "POST" and request.POST.get("confirm") == "yes":
            if action == "rotate":
                rotate_shipment_reference(obj, request.user)
            else:
                archive_shipment(obj, request.user, restore=action == "restore")
            messages.success(request, _("Shipment control saved. Previous public access may be revoked."))
            return HttpResponseRedirect(reverse("admin:shipments_shipment_change", args=[pk]))
        return TemplateResponse(request, "admin/shipments/confirm_control.html", {**self.admin_site.each_context(request), "title": _("Confirm shipment action"), "object": obj, "action": action, "opts": self.model._meta})


@admin.register(Customer)
class CustomerAdmin(RetainedAdmin):
    list_display = ("name", "company", "email", "phone")
    search_fields = ("name", "company", "email", "phone")
    readonly_fields = ("created_at",)

    def save_model(self, request, obj, form, change):
        obj.save()
        audit(obj, request.user, "customer.updated" if change else "customer.created", fields=form.changed_data)


class ChildAdmin(RetainedAdmin):
    autocomplete_fields = ("shipment",)
    list_filter = ("shipment__archived_at",)

    def has_change_permission(self, request, obj=None):
        return super().has_change_permission(request, obj) and not (obj and obj.shipment.archived_at)

    def save_model(self, request, obj, form, change):
        save_child(obj, request.user, form.changed_data)

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        try:
            return super().changeform_view(request, object_id, form_url, extra_context)
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
            return HttpResponseRedirect(request.path)


@admin.register(ShipmentItem)
class ItemAdmin(ChildAdmin):
    list_display = ("shipment", "description_en", "quantity", "unit", "cartons", "public")
    search_fields = ("description_en", "sku", "shipment__internal_order")
    list_filter = ChildAdmin.list_filter + ("public",)


@admin.register(TrackingLeg)
class LegAdmin(ChildAdmin):
    list_display = ("shipment", "sequence", "label", "carrier_identifier", "registration_state", "last_success")
    search_fields = ("label", "tracking_number", "shipment__internal_order")
    readonly_fields = ("registration_state", "last_success", "last_error", "provider_status")


@admin.register(TrackingEvent)
class EventAdmin(ChildAdmin):
    form = EventForm
    list_display = ("shipment", "occurred_at", "title_en", "mapped_status", "source", "public")
    list_filter = ChildAdmin.list_filter + ("source", "mapped_status", "public")
    search_fields = ("title_en", "shipment__internal_order")
    readonly_fields = ("source", "received_at", "creator", "provider_identity")
    ordering = ("-occurred_at",)


@admin.register(Document)
class DocumentAdmin(RetainedAdmin):
    list_display = ("shipment", "category", "original_filename", "size", "uploaded_at")
    list_filter = ("category", "shipment__archived_at")
    search_fields = ("shipment__internal_order", "original_filename")
    fields = ("shipment", "category", "original_filename", "mime_type", "size", "page_count", "checksum", "uploaded_by", "uploaded_at", "authorized_download")
    readonly_fields = fields

    def has_change_permission(self, request, obj=None):
        return False

    def authorized_download(self, obj):
        return format_html('<a href="{}">{}</a>', reverse("admin:shipments_document_download", args=[obj.pk]), _("Authorized download"))
    authorized_download.short_description = _("Private file")

    def get_urls(self):
        return [path("upload/", self.admin_site.admin_view(self.upload), name="shipments_document_upload"), path("<int:pk>/download/", self.admin_site.admin_view(self.download), name="shipments_document_download")] + super().get_urls()

    def add_view(self, request, form_url="", extra_context=None):
        require(request.user, "add_document")
        return HttpResponseRedirect(reverse("admin:shipments_document_upload"))

    def upload(self, request):
        require(request.user, "add_document")
        require(request.user, "view_shipment")
        form = DocumentUploadForm(request.POST or None, request.FILES or None, initial={"shipment": request.GET.get("shipment")})
        if request.method == "POST" and form.is_valid():
            try:
                obj = store_document(form.cleaned_data["shipment"], form.cleaned_data["upload"], form.cleaned_data["category"], form.inspection, request.user)
            except ValidationError as exc:
                form.add_error(None, exc)
            else:
                messages.success(request, _("Private document uploaded. It is never included in public tracking."))
                return HttpResponseRedirect(reverse("admin:shipments_document_change", args=[obj.pk]))
        return TemplateResponse(request, "admin/shipments/upload.html", {**self.admin_site.each_context(request), "title": _("Upload private document"), "form": form, "opts": self.model._meta})

    def download(self, request, pk):
        require(request.user, "view_document")
        require(request.user, "view_shipment")
        require(request.user, "download_document")
        obj = get_object_or_404(Document, pk=pk)
        try:
            opened = obj.file.open("rb")
        except (OSError, ValueError):
            raise Http404
        response = FileResponse(opened, as_attachment=True, filename=f"document-{obj.pk}" + {"application/pdf": ".pdf", "image/png": ".png", "image/jpeg": ".jpg"}[obj.mime_type], content_type=obj.mime_type)
        response["Cache-Control"] = "no-store, private"
        response["Content-Security-Policy"] = "sandbox; default-src 'none'"
        audit(obj, request.user, "document.downloaded")
        return response


@admin.register(AuditEntry)
class AuditAdmin(RetainedAdmin):
    list_display = ("created_at", "actor", "identity", "action", "object_type", "object_id", "shipment")
    list_filter = ("action", "object_type")
    search_fields = ("object_id",)
    fields = ("created_at", "actor", "identity", "shipment", "action", "object_type", "object_id", "changes")
    readonly_fields = fields

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
