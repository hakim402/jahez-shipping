from django.core.management.base import BaseCommand

class Command(BaseCommand):
    help = "Report the minimal role policy; does not assign permissions or create accounts."

    def handle(self, *args, **options):
        self.stdout.write("Foundation uses Django Users/Groups. Existing assignments are preserved; no operational role or account created.")
