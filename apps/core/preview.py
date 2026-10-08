"""Development-only synthetic UI fixtures. Never create or update shipments."""
from datetime import datetime, timezone

PREVIEW_STATES = (
    "initial", "submitting", "found", "invalid", "not_found",
    "rate_limited", "unavailable", "no_updates",
)


def synthetic_result(lang, no_updates=False):
    # Entirely invented for design review; explicitly labeled in the UI.
    # Each timestamp is a known fixture UTC instant, not operational evidence.
    ar = lang == "ar"
    event_specs = [
        ("2026-10-05T09:20:00+00:00", "manual", "Received at China warehouse", "وصلت إلى مستودع الصين", "Goods received and package details checked.", "تم استلام البضائع ومراجعة تفاصيل الطرود."),
        ("2026-10-06T14:00:00+00:00", "manual", "Preparing shipment", "تجهيز الشحنة", "The shipment is being prepared for the agreed freight route.", "يجري تجهيز الشحنة لمسار النقل المتفق عليه."),
        ("2026-10-07T16:00:00+00:00", "carrier", "Departed", "غادرت الشحنة", "A departure milestone was received from the carrier.", "ورد تحديث بمغادرة الشحنة من شركة النقل."),
        ("2026-10-09T08:10:00+00:00", "manual", "In transit", "قيد النقل", "JAHEZ published a newer freight update. Arrival estimate is not confirmed.", "نشرت جاهز تحديث نقل أحدث. لم يُؤكد تقدير الوصول."),
    ]
    events = []
    if not no_updates:
        for timestamp, source, title_en, title_ar, body_en, body_ar in event_specs:
            events.append({
                "occurred_at": datetime.fromisoformat(timestamp).astimezone(timezone.utc),
                "source": source,
                "title": title_ar if ar else title_en,
                "body": body_ar if ar else body_en,
            })
    return {"events": events, "no_updates": no_updates, "reference": "JHZ-DEMO-7K4P8Q2"}
