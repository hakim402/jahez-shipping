#!/usr/bin/env python3
"""Check staged files or published history without printing confidential values."""
import argparse
import re
import subprocess
from pathlib import PurePosixPath


PUBLIC_DOCS = {
    "17TRACK_INTEGRATION.md", "ADMIN_GUIDE.md", "AI_BEHAVIOR.md",
    "AI_SEARCH_TOOLS.md", "BACKUP_RESTORE.md", "DATA_MODEL.md",
    "DEPLOYMENT_VPS.md", "DOCUMENT_FIELD_MAPPING.md", "LOCAL_DEVELOPMENT.md",
    "NGINX_SSL.md", "OPERATIONS_RUNBOOK.md", "POSTGRES_MIGRATION.md",
    "RELEASE_0_8_1.md", "STATUS_RULES.md", "UPGRADE_ROLLBACK.md",
    "PUBLICATION_POLICY.md",
}
PRIVATE_DIRS = {
    "private", "data", "backups", "node_modules", ".venv", "venv",
    ".aws", ".ssh", ".codex", ".agents", "__pycache__", "staticfiles",
}
PRIVATE_SUFFIXES = {".db", ".sqlite3", ".sqlite", ".log", ".pem", ".key", ".p12", ".pfx", ".bundle"}
CONTENT_RULES = (
    ("private key", re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----")),
    ("GitHub credential", re.compile(rb"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{60,})\b")),
    ("Groq credential", re.compile(rb"\bgsk_[A-Za-z0-9]{40,}\b")),
    ("AWS credential", re.compile(rb"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("personal computer path", re.compile(rb"/(?:Users|home)/[A-Za-z0-9_.-]+/")),
    ("credential in URL", re.compile(rb"https?://[^\s/:]+:[^\s/@]+@")),
)


def git(*args):
    return subprocess.check_output(["git", *args])


def forbidden_path(name):
    path = PurePosixPath(name)
    lower = path.name.lower()
    if lower in {"agents.md", "project_prompt.md"}:
        return True
    if any(part.lower() in PRIVATE_DIRS for part in path.parts):
        return True
    if lower.startswith(".env") and name not in {".env.dev.example", ".env.prod.example"}:
        return True
    if path.suffix.lower() in PRIVATE_SUFFIXES or ".sqlite3-" in lower:
        return True
    if lower in {"id_rsa", "id_ed25519", "credentials", "credentials.json"}:
        return True
    if path.parts[0].lower() == "docs":
        return len(path.parts) != 2 or path.name not in PUBLIC_DOCS
    return False


def content_issues(data):
    return [label for label, pattern in CONTENT_RULES if pattern.search(data)]


def private_email(address):
    return not address.endswith(("@users.noreply.github.com", ".test"))


def trees(refs):
    commits = git("rev-list", *refs).decode().splitlines()
    for commit in commits:
        yield commit, git("ls-tree", "-r", "-z", commit)


def check(index=False, refs=()):
    errors = set()
    blobs = {}
    if index:
        records = [("index", git("ls-files", "--stage", "-z"))]
        identities = [git("var", name).decode() for name in ("GIT_AUTHOR_IDENT", "GIT_COMMITTER_IDENT")]
        emails = [re.search(r"<([^>]+)>", identity).group(1) for identity in identities]
    else:
        if not refs:
            refs = git("for-each-ref", "--format=%(refname)", "refs/heads", "refs/tags").decode().splitlines()
        records = trees(refs)
        emails = git("log", "--format=%ae%n%ce", *refs).decode().splitlines()
    if any(private_email(address) for address in emails):
        errors.add("commit metadata: use a GitHub noreply email")
    count = 0
    for revision, tree in records:
        count += 1
        for record in tree.split(b"\0"):
            if not record:
                continue
            meta, raw_name = record.split(b"\t", 1)
            fields = meta.decode().split()
            mode, oid = (fields[0], fields[1]) if index else (fields[0], fields[2])
            name = raw_name.decode("utf-8", "surrogateescape")
            if forbidden_path(name):
                errors.add(f"{name}: private path")
                continue
            if mode == "160000":
                errors.add(f"{name}: unreviewed submodule")
                continue
            if oid not in blobs:
                blobs[oid] = content_issues(git("cat-file", "blob", oid))
            for label in blobs[oid]:
                errors.add(f"{name}: {label}")
    if errors:
        print("Publication blocked (values are not displayed):")
        for error in sorted(errors):
            print(f"- {error}")
        return 1
    print(f"PASS: publication policy checked {count} {'index' if index else 'commits'} and {len(blobs)} unique file versions.")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", action="store_true", help="Check the complete staged tree")
    parser.add_argument("refs", nargs="*", help="Check every commit reachable from these refs; default: all branches/tags")
    args = parser.parse_args()
    if args.index and args.refs:
        parser.error("--index cannot be combined with refs")
    raise SystemExit(check(args.index, args.refs))


if __name__ == "__main__":
    main()
