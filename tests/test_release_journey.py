from pathlib import Path
import tempfile

from django.core.cache import cache
from django.test import TransactionTestCase, override_settings

from tests.release_journey import exercise


class ReleaseJourneyTests(TransactionTestCase):
    def test_complete_admin_refresh_public_daily_failure_manual_archive_lifecycle(self):
        with tempfile.TemporaryDirectory(prefix="jahez-release-journey-") as directory, \
             override_settings(DATA_DIR=Path(directory)):
            proof=exercise()
        self.assertEqual(proof["events"],4)
        self.assertTrue(all(value is True for key,value in proof.items() if key not in ("container_id","events")))
        cache.clear()
