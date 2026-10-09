from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.utils import timezone
from datetime import timedelta
from apps.shipments.models import Customer, Shipment, ShipmentItem, TrackingEvent, Status, AuditEntry
from apps.shipments.uploads import inspect_upload, store_document


def sample_pdf():
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
    import io
    writer = PdfWriter()
    page = writer.add_blank_page(width=595, height=842)
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica")})
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
    lines = ["SYNTHETIC DEMO SHIPPING BILL - NOT A REAL SHIPMENT", "Bill: DEMO-BILL-001", "Customer: DEMO Review Customer", "Origin: Mainland China", "Destination: United Arab Emirates", "Mode: Sea freight", "Product: DEMO reusable drinkware", "Quantity: 120 units", "Cartons: 6", "Weight: 42.500 kg", "Volume: 0.850 cubic metres", "No price, carrier number or confirmed arrival estimate supplied."]
    stream = DecodedStreamObject()
    content = "BT /F1 12 Tf 40 790 Td 20 TL " + " ".join("(" + line + ") Tj T*" for line in lines) + " ET"
    stream.set_data(content.encode("ascii"))
    page[NameObject("/Contents")] = writer._add_object(stream)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


class Command(BaseCommand):
    help = "Create labeled synthetic manual-review shipments and a private sample bill, development only."
    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("seed_demo is restricted to development.")
        call_command("setup_roles")
        now = timezone.now()
        with transaction.atomic():
            customer, _ = Customer.objects.get_or_create(name="DEMO Review Customer", company="DEMO — synthetic review only", defaults={"email": "demo@example.invalid", "notes": "Invented local fixture; not a real customer."})
            specs = [("DEMO-MANUAL", Status.TRANSIT, True, None), ("DEMO-NO-UPDATES", Status.CREATED, True, None), ("DEMO-OVERDUE", Status.CUSTOMS, False, now - timedelta(days=1)), ("DEMO-DELIVERED", Status.DELIVERED, False, now - timedelta(days=3))]
            samples = []
            for order, status, published, eta in specs:
                shipment = Shipment.objects.filter(is_demo=True, internal_order=order).first()
                if not shipment:
                    shipment = Shipment.objects.create(customer=customer, internal_order=order, bill_number="DEMO-BILL-001" if order == "DEMO-MANUAL" else "", is_demo=True, published=published, status=status, eta=eta, origin_en="Mainland China", origin_ar="الصين", destination_en="United Arab Emirates", destination_ar="الإمارات العربية المتحدة", internal_notes="DEMO private note - must never appear in public tracking.")
                    AuditEntry.objects.create(identity="seed_demo", shipment=shipment, object_type="shipment", object_id=str(shipment.pk), action="demo.created")
                samples.append(shipment)
            shipment = samples[0]
            ShipmentItem.objects.get_or_create(shipment=shipment, sku="DEMO-PUBLIC", defaults={"description_en": "DEMO reusable drinkware", "description_ar": "أكواب تجريبية", "quantity": 120, "unit": "units", "unit_ar": "قطعة", "cartons": 6, "weight_kg": "42.500", "volume_cbm": "0.850", "public": True})
            ShipmentItem.objects.get_or_create(shipment=shipment, sku="DEMO-PRIVATE", defaults={"description_en": "DEMO confidential spare parts", "quantity": 2, "public": False})
            for days, status, en, ar in [(3, Status.WAREHOUSE, "DEMO goods received", "استلام بضائع تجريبية"), (1, Status.TRANSIT, "DEMO manual freight update", "تحديث نقل يدوي تجريبي")]:
                TrackingEvent.objects.get_or_create(shipment=shipment, title_en=en, defaults={"occurred_at": now - timedelta(days=days), "mapped_status": status, "title_ar": ar, "body_en": "Synthetic milestone entered by the review command.", "body_ar": "مرحلة توضيحية أدخلها أمر المراجعة.", "public": True})
        if not shipment.documents.exists():
            upload = SimpleUploadedFile("DEMO-shipping-bill.pdf", sample_pdf(), content_type="application/pdf")
            metadata = inspect_upload(upload)
            # Command identity is explicitly synthetic; no user or password is created.
            store_document(shipment, upload, "bill", metadata, actor=None, system_demo=True)
        self.stdout.write(self.style.SUCCESS("DEMO records ready. No customer account or admin password created. References are private: copy them from the authorized shipment admin, not logs."))
