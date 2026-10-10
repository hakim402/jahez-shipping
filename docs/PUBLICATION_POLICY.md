# Publication policy

Owner instructions (`AGENTS.md`, `PROJECT_PROMPT.md`), internal project/phase notes, account setup evidence and review screenshots are local-only. Do not force-add or upload them. Actual environments, credentials, databases, private uploads, backups and key files are also excluded. Public environment examples contain placeholders only. Reviewed technical and deployment guides remain available; account credentials and host-specific inventory belong in private operational records.

After cloning, enable the repository hooks:

```bash
git config --local core.hooksPath .githooks
git config --local user.email YOUR_GITHUB_NOREPLY_ADDRESS
python3 scripts/check_publication.py --index
python3 scripts/check_publication.py
```

Use the noreply address from your GitHub email settings, never a personal email address. The hooks block private commit email metadata, excluded files and recognized credentials, and check every commit reachable from each pushed branch/tag. The checks report file names and categories without showing matched values. A GitHub workflow independently checks incoming history. New public documentation requires review and an explicit addition to the documentation allowlist and `.gitignore` exceptions.

These checks reduce accidental disclosure; they cannot identify every possible secret or prevent a person deliberately bypassing hooks. Review staged changes before publication. Never disable these hooks to push private files.

If confidential content was already pushed, removing a file in a new commit is insufficient. Remove it from affected branch and tag history, coordinate any shared clones, and rotate exposed credentials. GitHub caches, unreachable commit links, forks and existing clones require separate handling; contact GitHub Support for retained sensitive content. Keep any recovery bundle strictly private and outside Git and build contexts.
