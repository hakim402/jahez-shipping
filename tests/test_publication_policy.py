"""Publication checks run without Django, provider credentials or real records."""
import contextlib
import io
import os
import subprocess
import tempfile
import unittest
import shutil
from pathlib import Path

from scripts.check_publication import check, content_issues, forbidden_path


class PublicationPolicyTests(unittest.TestCase):
    def test_private_paths_even_if_force_added(self):
        for name in ("AGENTS.md", "PROJECT_PROMPT.md", "nested/agents.md", ".env.prod",
                     "private/snapshot.tar.gz", "data/upload.pdf", "backup.bundle",
                     "docs/PROGRESS.md", "docs/archive/pre-container-20261016/README.md", "docs/AI_BEHAVIOR.md", "docs/screenshots/admin.jpg", "key.pem",
                     "db.sqlite3-wal", ".ssh/id_rsa"):
            with self.subTest(name=name):
                self.assertTrue(forbidden_path(name))

    def test_public_runtime_and_reviewed_guides(self):
        for name in (".env.dev.example", ".env.prod.example", "docs/DEPLOYMENT_VPS.md",
                     "apps/shipments/models.py", "docs/CONTAINER_DESIGN.md", "static/images/majed-saleem.webp"):
            self.assertFalse(forbidden_path(name))

    def test_old_public_guides_do_not_allow_private_archive_or_current_stale_guides(self):
        self.assertTrue(forbidden_path("docs/AI_BEHAVIOR.md"))
        self.assertFalse(forbidden_path("docs/AI_BEHAVIOR.md", historical=True))
        self.assertTrue(forbidden_path("docs/archive/AI_BEHAVIOR.md", historical=True))

    def test_sensitive_content_reports_categories_only(self):
        fixtures = [b"gsk_" + b"x" * 48, b"ghp_" + b"x" * 40,
                    b"-----BEGIN " + b"PRIVATE KEY-----",
                    b"/" + b"Users/example/private/", b"https://" + b"user:password@example.test"]
        for data in fixtures:
            self.assertTrue(content_issues(data))
        self.assertEqual(content_issues(b"GROQ_API_KEY=<your-private-key>"), [])

    @unittest.skipUnless(shutil.which("git"), "Git history test runs on the host/CI; Git is absent from minimal runtime.")
    def test_checks_staged_blobs_and_old_history(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def run(*args):
                subprocess.run(["git", *args], cwd=root, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            run("init")
            run("config", "user.name", "Publication test")
            run("config", "user.email", "test@example.test")
            (root / ".gitignore").write_text("AGENTS.md\n")
            (root / "AGENTS.md").write_text("private instructions")
            run("add", ".gitignore")
            run("add", "-f", "AGENTS.md")
            previous = os.getcwd()
            try:
                os.chdir(root)
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(check(index=True), 1)
                run("commit", "-m", "Test private history")
                run("rm", "AGENTS.md")
                run("commit", "-m", "Remove from current tree")
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(check(index=True), 0)
                    self.assertEqual(check(refs=("HEAD",)), 1)
                run("config", "user.email", "private@example.com")
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(check(index=True), 1)
            finally:
                os.chdir(previous)
