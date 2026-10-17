import apps.containers.values
import django.core.validators
import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('shipments', '0004_retire_customer_workflows'),
    ]

    operations = [
        migrations.CreateModel(
            name='Container',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('journey_key', models.UUIDField(default=uuid.uuid4, editable=False, help_text='Internal journey grouping; use a new key for a later journey, even with the same container.', verbose_name='Journey key')),
                ('search_reference', models.CharField(max_length=40, validators=[django.core.validators.RegexValidator('\\A[A-Z0-9][A-Z0-9-]{5,39}\\Z', 'Use a carrier search reference of 6 to 40 uppercase letters, digits or hyphens.')], verbose_name='B/L or search reference')),
                ('container_number', models.CharField(blank=True, default='', help_text='Leave empty until the carrier identifies one container or an administrator selects it.', max_length=11, validators=[django.core.validators.RegexValidator('\\A(?:[A-Z]{4}[0-9]{7})?\\Z', 'Use four uppercase letters and seven digits, or leave the container unbound.')], verbose_name='Container number')),
                ('source_adapter', models.CharField(choices=[('sealegend-web-proof-v1', 'Sea Legend')], default='sealegend-web-proof-v1', max_length=64, verbose_name='Source adapter')),
                ('source_website', models.URLField(choices=[('https://www.slg-shipping.com/#/home/tracking', 'Sea Legend')], default='https://www.slg-shipping.com/#/home/tracking', verbose_name='Source website')),
                ('equipment_type', models.CharField(blank=True, max_length=32, verbose_name='Equipment type')),
                ('equipment_quantity', models.PositiveSmallIntegerField(blank=True, null=True, validators=[django.core.validators.MinValueValidator(1)], verbose_name='Equipment quantity')),
                ('origin_code', models.CharField(blank=True, max_length=16, verbose_name='Origin code')),
                ('destination_code', models.CharField(blank=True, max_length=16, verbose_name='Destination code')),
                ('origin_label_en', models.CharField(blank=True, max_length=200, verbose_name='Origin label (English)')),
                ('origin_label_ar', models.CharField(blank=True, max_length=200, verbose_name='Origin label (Arabic)')),
                ('destination_label_en', models.CharField(blank=True, max_length=200, verbose_name='Destination label (English)')),
                ('destination_label_ar', models.CharField(blank=True, max_length=200, verbose_name='Destination label (Arabic)')),
                ('vessel', models.CharField(blank=True, max_length=200, verbose_name='Vessel')),
                ('voyage', models.CharField(blank=True, max_length=80, verbose_name='Voyage')),
                ('raw_status', models.CharField(blank=True, max_length=256, verbose_name='Raw carrier status')),
                ('carrier_status', models.CharField(choices=[('unknown', 'Needs review'), ('preparing', 'Preparing'), ('in_transit', 'In transit'), ('arrived', 'Arrived'), ('customs', 'Customs'), ('ready', 'Ready for collection'), ('completed', 'Completed'), ('on_hold', 'On hold')], default='unknown', max_length=20, verbose_name='Carrier status')),
                ('departure_actual', models.JSONField(blank=True, null=True, validators=[apps.containers.values.validate_source_time], verbose_name='Actual departure')),
                ('departure_estimated', models.JSONField(blank=True, null=True, validators=[apps.containers.values.validate_source_time], verbose_name='Estimated departure')),
                ('arrival_actual', models.JSONField(blank=True, null=True, validators=[apps.containers.values.validate_source_time], verbose_name='Actual arrival')),
                ('arrival_estimated', models.JSONField(blank=True, null=True, validators=[apps.containers.values.validate_source_time], verbose_name='Estimated arrival')),
                ('manual_notes_en', models.TextField(blank=True, max_length=2000, verbose_name='Manual notes (English)')),
                ('manual_notes_ar', models.TextField(blank=True, max_length=2000, verbose_name='Manual notes (Arabic)')),
                ('manual_status_override', models.CharField(blank=True, choices=[('unknown', 'Needs review'), ('preparing', 'Preparing'), ('in_transit', 'In transit'), ('arrived', 'Arrived'), ('customs', 'Customs'), ('ready', 'Ready for collection'), ('completed', 'Completed'), ('on_hold', 'On hold')], default=None, help_text='Empty uses the carrier status. Manual notes remain independent of carrier updates.', max_length=20, null=True, verbose_name='Manual status override')),
                ('is_published', models.BooleanField(default=False, verbose_name='Published')),
                ('archived_at', models.DateTimeField(blank=True, null=True, verbose_name='Archived at')),
                ('lookup_code', models.CharField(default=apps.containers.values.lookup_code, editable=False, max_length=30, unique=True, validators=[django.core.validators.RegexValidator('\\AJHZ-[A-Z2-7]{26}\\Z', 'Use the generated JAHEZ lookup code.')], verbose_name='JAHEZ lookup code')),
                ('last_refresh_attempt_at', models.DateTimeField(blank=True, null=True, verbose_name='Last refresh attempt')),
                ('last_refresh_success_at', models.DateTimeField(blank=True, null=True, verbose_name='Last successful refresh')),
                ('last_failure_code', models.CharField(blank=True, choices=[('ai_unavailable', 'ai_unavailable'), ('ambiguous_container', 'ambiguous_container'), ('blocked_address', 'blocked_address'), ('concurrent_change', 'concurrent_change'), ('identity_mismatch', 'identity_mismatch'), ('invalid_extraction', 'invalid_extraction'), ('invalid_reference', 'invalid_reference'), ('not_found', 'not_found'), ('redirect_refused', 'redirect_refused'), ('source_changed', 'source_changed'), ('timeout', 'timeout'), ('too_large', 'too_large'), ('unavailable', 'unavailable'), ('unknown_status', 'unknown_status')], max_length=32, verbose_name='Refresh failure code')),
                ('source_fingerprint', models.CharField(blank=True, max_length=64, validators=[django.core.validators.RegexValidator('\\A[0-9a-f]{64}\\Z', 'Use a SHA-256 fingerprint.')], verbose_name='Source fingerprint')),
                ('source_evidence', models.JSONField(blank=True, default=dict, validators=[apps.containers.values.validate_evidence], verbose_name='Accepted source evidence')),
                ('revision', models.PositiveBigIntegerField(default=0, editable=False, verbose_name='Revision')),
                ('refresh_claim', models.UUIDField(blank=True, editable=False, null=True, verbose_name='Refresh claim')),
                ('refresh_claim_expires_at', models.DateTimeField(blank=True, editable=False, null=True, verbose_name='Refresh claim expiry')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Created at')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated at')),
            ],
            options={
                'verbose_name': 'Container',
                'verbose_name_plural': 'Containers',
                'ordering': ['-created_at', '-pk'],
                'constraints': [models.UniqueConstraint(fields=('journey_key', 'source_adapter', 'search_reference', 'container_number'), name='container_journey_identity'), models.CheckConstraint(condition=models.Q(('equipment_quantity__isnull', True), ('equipment_quantity__gte', 1), _connector='OR'), name='container_positive_quantity'), models.CheckConstraint(condition=models.Q(models.Q(('refresh_claim__isnull', True), ('refresh_claim_expires_at__isnull', True)), models.Q(('refresh_claim__isnull', False), ('refresh_claim_expires_at__isnull', False)), _connector='OR'), name='container_claim_pair')],
            },
        ),
        migrations.CreateModel(
            name='ContainerEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('origin', models.CharField(choices=[('carrier', 'Carrier'), ('manual', 'Manual')], default='manual', max_length=7, verbose_name='Origin')),
                ('source_event_id', models.CharField(blank=True, max_length=128, verbose_name='Source event ID')),
                ('source_leg', models.CharField(blank=True, help_text='Stable source leg identity when a journey revisits a location; never a retrieval time.', max_length=128, verbose_name='Source leg')),
                ('location_code', models.CharField(blank=True, max_length=16, verbose_name='Location code')),
                ('location', models.CharField(blank=True, max_length=256, verbose_name='Source location')),
                ('raw_status', models.CharField(blank=True, max_length=256, verbose_name='Raw source status')),
                ('raw_text', models.TextField(blank=True, max_length=2000, verbose_name='Raw source text')),
                ('designation', models.CharField(choices=[('unknown', 'Unknown'), ('actual', 'Actual'), ('estimated', 'Estimated')], default='unknown', max_length=9, verbose_name='Actual or estimated')),
                ('source_time', models.JSONField(blank=True, null=True, validators=[apps.containers.values.validate_source_time], verbose_name='Source time')),
                ('title_en', models.CharField(blank=True, max_length=200, verbose_name='Title (English)')),
                ('title_ar', models.CharField(blank=True, max_length=200, verbose_name='Title (Arabic)')),
                ('detail_en', models.TextField(blank=True, max_length=2000, verbose_name='Detail (English)')),
                ('detail_ar', models.TextField(blank=True, max_length=2000, verbose_name='Detail (Arabic)')),
                ('is_public', models.BooleanField(default=False, verbose_name='Public event')),
                ('dedupe_key', models.CharField(blank=True, editable=False, max_length=64, validators=[django.core.validators.RegexValidator('\\A[0-9a-f]{64}\\Z', 'Use a SHA-256 fingerprint.')], verbose_name='Deduplication key')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Created at')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated at')),
                ('container', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='events', to='containers.container', verbose_name='Container')),
            ],
            options={
                'verbose_name': 'Container event',
                'verbose_name_plural': 'Container events',
                'ordering': ['created_at', 'pk'],
                'constraints': [models.UniqueConstraint(fields=('container', 'origin', 'dedupe_key'), name='container_event_identity')],
            },
        ),
    ]
