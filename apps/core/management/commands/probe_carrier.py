"""Explicit local proof; never connected to public views or application records."""
import getpass
import json
import os
import sys
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from apps.integrations.sealegend import MAX_BYTES, SourceError, parse_candidate, retrieve_candidate


class Command(BaseCommand):
    help = "Probe pinned Sea Legend source without database/AI calls; only summary counts are printed."
    requires_system_checks = []
    requires_migrations_checks = False

    def add_arguments(self, parser):
        parser.add_argument("--stdin", action="store_true", help="Read B/L from stdin, never process arguments.")
        parser.add_argument("--from-file", type=Path, help="Normalize a bounded carrier JSON export offline.")
        parser.add_argument("--save-private", action="store_true", help="Save candidate to ignored private/source-proof/candidate.json (replaces previous proof).")

    def handle(self, *args, **options):
        if not options["stdin"] and not sys.stdin.isatty():
            raise CommandError("Use --stdin for noninteractive input.")
        reference = sys.stdin.readline(42).strip() if options["stdin"] else getpass.getpass("Carrier B/L (hidden): ")
        try:
            if options["from_file"]:
                with options["from_file"].open("rb") as stream:
                    candidate = parse_candidate(stream.read(MAX_BYTES + 1), reference)
            else:
                candidate = retrieve_candidate(reference)
            if options["save_private"]:
                root = Path(__file__).resolve().parents[4]
                directory = root / "private" / "source-proof"
                for part in (root / "private", directory):
                    if part.is_symlink():
                        raise CommandError("private_capture_refused")
                    part.mkdir(mode=0o700, exist_ok=True)
                    part.chmod(0o700)
                path = directory / "candidate.json"
                # No arbitrary output path, no symlink following, one bounded replaceable capture.
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
                with os.fdopen(fd, "w") as stream:
                    os.fchmod(stream.fileno(), 0o600)
                    json.dump(candidate, stream, ensure_ascii=False, indent=2)
        except SourceError as exc:
            raise CommandError(exc.code) from None
        except OSError:
            raise CommandError("source_or_private_file_unavailable") from None
        count = len(candidate["containers"])
        self.stdout.write(f"Candidate only: {count} container(s); selection_required={candidate['container_selection_required']}; no records saved.")
