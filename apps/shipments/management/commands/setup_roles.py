from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create/update shipping role groups; does not create users or assign access."

    def handle(self, *args, **options):
        permissions = Permission.objects.filter(content_type__app_label="shipments")
        operations = permissions.exclude(codename__startswith="delete_").exclude(content_type__model="auditentry")
        operations = list(operations) + list(permissions.filter(codename="view_auditentry"))
        readonly = permissions.filter(codename__startswith="view_")
        for name, selected in [("Shipping Operations", operations), ("Shipping Read Only", readonly)]:
            group, _ = Group.objects.get_or_create(name=name)
            group.permissions.set(selected)
        self.stdout.write(self.style.SUCCESS("Shipping role groups ready. Assign only intended staff through Users. No account/password created."))
