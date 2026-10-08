from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
class Command(BaseCommand):
    help = "Confirm the development-only foundation preview; no customer or shipment data is created."
    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("seed_demo is restricted to development.")
        self.stdout.write(self.style.SUCCESS("Foundation preview is ready. Synthetic content is template-only; no records or admin passwords created."))
