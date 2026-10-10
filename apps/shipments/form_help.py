"""Short, translated field guidance shared by admin pages and shipment inlines."""
from django.utils.translation import gettext_lazy as _
from django.utils.text import format_lazy
from django.conf import settings

HELP = {
    "customer": _("Select the customer, or use + to add one. Contact details stay private."),
    "shipment": _("Select the shipment this record belongs to."),
    "name": _("Enter the customer's full name. It is visible only to staff."),
    "company": _("Optional: the customer's business name."),
    "phone": _("Include the country code, for example +86. This number stays private."),
    "email": _("Optional contact address. It is never shown in public tracking."),
    "address": _("Private delivery or contact address. Leave blank if not yet known."),
    "notes": _("Notes for your team only."),
    "internal_notes": _("Notes for your team only."),
    "internal_order": _("Your team's order number. Customers track with the separate JAHEZ reference."),
    "bill_number": _("Optional shipping bill number for your records. It stays private."),
    "mode": _("Choose how the goods will travel."),
    "tracking_mode": _("Choose Manual for team updates, Carrier tracking for a supported carrier, or both."),
    "status": _("Choose the shipment's current stage. Adding a timeline update does not change this field."),
    "origin_en": _("Public starting country or region in English. Avoid private addresses."),
    "origin_ar": _("The same starting country or region in Arabic."),
    "destination_en": _("Public destination country or region in English. Avoid private addresses."),
    "destination_ar": _("The same destination country or region in Arabic."),
    "eta": _("Enter an arrival estimate only when confirmed. Leave blank when unknown."),
    "actual_arrival": _("When the shipment actually reached its destination. Leave blank until confirmed."),
    "delivered_at": _("When the customer actually received the shipment. Leave blank until confirmed."),
    "published": _("Enable only after reviewing both languages. This makes approved tracking details visible to the customer."),
    "confirmed_delay": _("Use only for a confirmed delay; explain it in the reason field."),
    "delay_reason": _("Explain the confirmed delay for your team. This text stays private."),
    "status_locked": _("Keep carrier updates from changing the status you selected. A reason is required."),
    "override_reason": _("Explain why your team is keeping this status. This text stays private."),
    "correction_reason": _("Required when correcting a completed status, moving backward, or releasing a status lock."),
    "confirm_complete_shipment": _("Confirm only when every package and shipment stage has been delivered."),
    "carrier_coverage_complete": _("Enable only when these carrier references cover every package in this shipment."),
    "description_en": _("A clear product name in English. Leave prices and private supplier details out."),
    "description_ar": _("The same product name in Arabic. Required for a public item."),
    "quantity": _("Enter the total quantity as a positive number."),
    "unit": _("English unit, for example pieces, boxes or kilograms."),
    "unit_ar": _("The same unit in Arabic. Required for a public item."),
    "cartons": _("Optional number of cartons. Leave blank when unknown."),
    "sku": _("Optional internal product code. It stays private."),
    "weight_kg": _("Total weight in kilograms, if known."),
    "volume_cbm": _("Total volume in cubic metres, if known."),
    "sequence": _("Number the shipment stages in order, starting with 1."),
    "label": _("Optional label for your team, for example air freight or final delivery."),
    "carrier_identifier": _("The carrier's numeric 17TRACK code. Leave blank for a manual reference."),
    "tracking_number": _("Use the carrier-issued tracking number, not the customer's JAHEZ reference."),
    "occurred_at": _("When this update happened, using the timezone shown by the form. Do not enter a future time."),
    "title_en": _("A short customer-friendly milestone title in English."),
    "title_ar": _("The same milestone title in Arabic. Required for publication."),
    "body_en": _("Optional detail in English. Keep contacts, prices and private addresses out."),
    "body_ar": _("Translate the English detail into Arabic before publishing."),
    "mapped_status": _("The stage described by this update. Set the overall shipment status separately."),
    "public": _("Publish only after reviewing the English and Arabic text."),
    "leg": _("Optional carrier reference from this same shipment."),
    "raw_text": _("Original source wording for staff review only."),
    "location": _("Detailed location for staff only. It is not shown publicly."),
    "category": _("Choose the document type so your team can find it later."),
    "upload": _("Choose a PDF, PNG or JPEG up to 5 MiB. The file stays private."),
}


def apply_help(form):
    for name, field in form.fields.items():
        if name in HELP:
            field.help_text = HELP[name]
        if name in ("eta", "actual_arrival", "delivered_at", "occurred_at"):
            field.help_text = format_lazy("{} {}", field.help_text,
                _("Timezone: %(timezone)s.") % {"timezone": settings.BUSINESS_TIME_ZONE})
