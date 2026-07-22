---
name: ship
description: Land a finished code change on main via the branch → full test suite → PR → CI → auto-merge flow this repo requires. Use whenever a change is ready to commit and merge (main is protected — you cannot push to it directly).
---

`main` is protected: PR-only, with two required CI checks (`Test suite (Postgres)`
and `Production image builds`). You cannot push to `main` — every change goes
through this flow. Do not skip the local full-suite run: CI takes ~7 min, the
local suite ~2 min, and catching a failure locally avoids a red CI run.

## Steps

```bash
# 1. Branch (never commit on main — the push will be rejected).
git checkout -b <short-kebab-branch>

# 2. Run the FULL suite locally. --parallel auto needs tblib (in
#    requirements-dev.txt) or a failure crashes the runner with
#    "cannot pickle 'traceback'" instead of reporting. Capture the true
#    exit code with pipestatus — a bare pipe reports the grep's status,
#    which masks a failed run.
./venv3-13/bin/python manage.py test --parallel auto 2>&1 | grep -E "^(Ran|OK|FAILED)"; echo "exit: ${pipestatus[1]}"

# 3. If a migration-bearing change: confirm none are missing.
./venv3-13/bin/python manage.py makemigrations --check --dry-run

# 4. Commit. End the message with:
#      Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
git add <paths> && git commit -m "..."

# 5. Push the branch, open the PR (use "Fixes #N" to auto-close its issue),
#    arm auto-merge, return to main.
git push -u origin <branch>
gh pr create -R jwincek/oilregionindie.com -t "..." -b "Fixes #N. ..."
gh pr merge <branch> -R jwincek/oilregionindie.com --auto --merge
git checkout main

# 6. Watch CI to completion, then sync + clean up once merged.
gh pr checks <N> -R jwincek/oilregionindie.com --watch
git pull --ff-only origin main
git branch -d <branch>
```

## Conventions this repo follows

- **Issue first** for anything with a story worth preserving (a bug's root
  cause, a design decision, deferred work) — file it, then reference it with
  `Fixes #N`. Skip the issue only for typo-tier changes where the diff is the
  whole story.
- **PR body** ends with the `🤖 Generated with [Claude Code]` trailer.
- Auto-merge fires only after both required checks pass, so arming it and
  walking away is safe; the watch in step 6 is just to confirm and sync.

## Adapting to a similar project (e.g. recruiter_project)

Change the repo slug, the two CI check names (match that project's
`.github/workflows`), the venv path, and the co-author trailer if different.
The shape — branch, local suite, PR, arm auto-merge, watch, sync — is identical.
