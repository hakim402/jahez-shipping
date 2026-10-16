"""Owner-authorized schema cleanup; restore a matching backup to recover data."""
from django.db import migrations
from apps.core.transition import require_legacy_backup

class Migration(migrations.Migration):
    dependencies = [('ai', '0002_operational_assistant'), ('shipments', '0003_fileremoval_alter_auditentry_shipment_and_more'), ('tracking', '0001_initial'), ('sessions', '0001_initial'), ('admin', '0003_logentry_add_action_flag_choices'), ('contenttypes', '0002_remove_content_type_name'), ('auth', '0012_alter_user_first_name_max_length')]
    operations = [migrations.RunPython(require_legacy_backup),
        migrations.DeleteModel(name='AIDraft'),
        migrations.DeleteModel(name='AssistantRun'),
    ]
