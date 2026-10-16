"""Owner-authorized schema cleanup; restore a matching backup to recover data."""
from django.db import migrations
from apps.core.transition import remove_retired_permissions

class Migration(migrations.Migration):
    dependencies = [('shipments', '0003_fileremoval_alter_auditentry_shipment_and_more'), ('ai', '0003_retire_ai_workflows'), ('tracking', '0002_retire_carrier_workflows')]
    operations = [migrations.RunPython(migrations.RunPython.noop),
        migrations.DeleteModel(name='AuditEntry'),
        migrations.DeleteModel(name='Document'),
        migrations.DeleteModel(name='TrackingEvent'),
        migrations.DeleteModel(name='ShipmentItem'),
        migrations.DeleteModel(name='TrackingLeg'),
        migrations.DeleteModel(name='Shipment'),
        migrations.DeleteModel(name='Customer'),
        migrations.DeleteModel(name='FileRemoval'),
        migrations.RunPython(remove_retired_permissions),
    ]
