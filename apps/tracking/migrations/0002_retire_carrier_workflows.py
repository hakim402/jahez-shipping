"""Owner-authorized schema cleanup; restore a matching backup to recover data."""
from django.db import migrations

class Migration(migrations.Migration):
    dependencies = [('tracking', '0001_initial'), ('ai', '0003_retire_ai_workflows')]
    operations = [migrations.RunPython(migrations.RunPython.noop),
        migrations.DeleteModel(name='IntegrationJob'),
        migrations.DeleteModel(name='WebhookReceipt'),
    ]
