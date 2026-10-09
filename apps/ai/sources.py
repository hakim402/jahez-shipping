"""Explicit minimal allowlist and complete private change fingerprint, no contact/capability."""
import hashlib
import json
from django.utils import timezone
from apps.shipments.models import Shipment
from .provider import AIError


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def version(shipment):
    # Child edits also invalidate drafts, even though legacy child services do not bump revision.
    ship = Shipment.objects.get(pk=shipment.pk)
    values = {f.name: str(getattr(ship, f.name)) for f in ship._meta.fields}
    values['items'] = list(ship.items.order_by('pk').values())
    values['events'] = list(ship.events.order_by('pk').values())
    values['legs'] = list(ship.legs.order_by('pk').values())
    values['documents'] = list(ship.documents.order_by('pk').values('pk', 'checksum', 'category'))
    return digest(values)


def build_history(shipment, event=None):
    record = {'id': 'shipment', 'status': shipment.status, 'updated_at': shipment.updated_at.isoformat(),
        'observed_at': shipment.status_observed_at.isoformat() if shipment.status_observed_at else None,
        'origin': [shipment.origin_en, shipment.origin_ar], 'destination': [shipment.destination_en, shipment.destination_ar],
        'eta': shipment.eta.isoformat() if shipment.eta else None, 'delivered_at': shipment.delivered_at.isoformat() if shipment.delivered_at else None,
        'confirmed_delay': shipment.confirmed_delay}
    records = [record]
    events = [event] if event else list(shipment.events.order_by('-received_at', '-pk')[:20])
    warnings = ['Private AI suggestion. Verify every claim against its source before approving.', 'No new ETA, delay cause or delivery confirmation may be inferred.']
    if shipment.events.count() > 20 and not event:
        warnings.append('History is incomplete: only the latest 20 received events are included.')
    for row in events:
        text = row.raw_text if event else row.title_en + '\n' + row.title_ar + '\n' + row.body_en + '\n' + row.body_ar
        if len(text) > 4000:
            raise AIError('source_limit')
        records.append({'id': f'event:{row.pk}', 'text': text, 'occurred_at': row.occurred_at.isoformat() if row.occurred_at else None,
            'received_at': row.received_at.isoformat(), 'source': row.source, 'mapped_status': row.mapped_status})
    legs = list(shipment.legs.all())
    if any(not leg.last_success or timezone.now() - leg.last_success > timezone.timedelta(hours=24) for leg in legs):
        warnings.append('Carrier synchronization is missing or stale; it does not prove a business delay.')
    if not events:
        warnings.append('No event history is available.')
    if not record['eta']:
        warnings.append('Arrival estimate is unknown.')
    if not event:
        for item in shipment.items.order_by('pk')[:25]:
            records.append({'id': f'item:{item.pk}', 'product': [item.description_en, item.description_ar], 'quantity': str(item.quantity), 'unit': [item.unit, item.unit_ar]})
        if shipment.items.count() > 25:
            warnings.append('Products are incomplete: only the first 25 are included.')
    return {'records': records, 'warnings': warnings, 'images': []}
