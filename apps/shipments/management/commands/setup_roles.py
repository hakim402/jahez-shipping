from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create/update shipping role groups; does not create users or assign access."

    def handle(self, *args, **options):
        permissions = Permission.objects.filter(content_type__app_label="shipments")
        operations = permissions.exclude(codename__startswith="delete_").exclude(content_type__model="auditentry")
        operations = list(operations) + list(permissions.filter(codename="view_auditentry"))
        tracking = Permission.objects.filter(content_type__app_label="tracking")
        operations += list(tracking.filter(codename__in=["view_integrationjob", "view_webhookreceipt", "register_reference", "refresh_reference", "retry_jobs"]))
        readonly = list(permissions.filter(codename__startswith="view_")) + list(tracking.filter(codename__startswith="view_"))
        ai = Permission.objects.filter(content_type__app_label="ai")
        operations += list(ai.filter(codename__in=["view_aidraft", "request_ai", "review_ai", "apply_extraction", "retry_ai"]))
        readonly += list(ai.filter(codename="view_aidraft"))
        for name, selected in [("Shipping Operations", operations), ("Shipping Read Only", readonly)]:
            group, _ = Group.objects.get_or_create(name=name)
            group.permissions.set(selected)
        self.stdout.write(self.style.SUCCESS("Shipping role groups ready. Assign only intended staff through Users. No account/password created."))
