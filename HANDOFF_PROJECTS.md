# Project Coach handoff — updated 2026-11-16

Branch `project-coach` (from local `v4-outcomes`). Nothing pushed or merged. Work uses the data copy
`D:\LocalAI\signaldesk-v4-copy` only; the live home `D:\LocalAI\signaldesk` is untouched.

## Part 1 — state found on 2026-11-16 (all re-run, not taken from the old handoff)
- Both branches clean. pytest 314 passed; eval 19/19; tsc clean; oxlint 0 errors, 14 old warnings;
  desktop and mobile builds pass. `.venv` works here (Codex's sandbox could not run it).
- Step 1 was fixture-tested only; Steps 2–4 not started (schema, Mobile.tsx, notifications untouched).
- Review findings fixed since: hard-coded "Why it matters" (now sourced and validated), timestamp
  ordering across time zones, generic export errors, duplicate nav icon, raw-dump job-fit cards,
  whole data sheet shown as evidence. Open: SignalDesk cards carry full article text and profile-fact
  notes, so the cloud copy needs a reduced payload (Step 2).

## Step 1 — collector, task model, desktop page: run on real data
- Copy config has three `[[project]]` entries (backup: `config.toml.before-projects`; DB backup:
  `D:\LocalAI\signaldesk-v4-copy-db-before-projects.db`).
- Real collection: 3 tasks (nextword 1, signaldesk 2) + 1 pushback laptop reminder, because all 60
  pushback rows are labelled ("All 60 rows ... already have a human_label"; no model run).
- Answered in the browser: job-fit (unsure) and tutor answer (minor) on the copy; label task (unclear)
  on a scratch fixture home with 3 blanked rows (real pushback has none). Every note reads
  "TEST ANSWER (Claude), not a real review" — they must never be written back to a clone.
- Skip, refresh (no second allowance), missing-verdict error, export: all checked in the browser.
- Exports: pushback CSV (sheet columns + human_at, input_origin), nextword ZIP (4 sheets, key.json,
  audit JSON), signaldesk JSON v1. Checked by opening the files.
- Blindness: API and rendered page scanned for grader verdict/reason/score — none. Tests cover the
  API, stored snapshots, NextWord checks/pass/ai_review/model names.
- "Why it matters": README line + counts, re-verified at collection; `check_why` rejects generic text
  (tests). Rendered at 390 (light, dark) and 1440/1728 via headless Chrome; no horizontal scroll.
  Spacing measured at 390: 0 critical/serious. 1440/1728 not re-measured after the card reorder.
  Comprehension check: pass.

## Next
Step 2 cloud sync (needs owner to run SQL), Step 3 phone tab, Step 4 notifications, Parts 3–5.

## Commands
```
.venv\Scripts\python -m pytest -q
.venv\Scripts\python -m signaldesk.projects collect --home D:\LocalAI\signaldesk-v4-copy
.venv\Scripts\python -m signaldesk --home D:\LocalAI\signaldesk-v4-copy --no-start-model --port 8793
```
Owner rules: ask before live Supabase changes, first write/push in pushback or nextword, any push to
main, merge, scheduled task, firewall/LAN/tunnel changes. Nothing private in Git or logs.

## Update 2026-11-16 (later) — Steps 2–4 built, Part 3 built and stopped by real checks
- Step 2: cloud/project_coach.sql (NOT yet run on live Supabase — owner must run it), coach_sync.py,
  verify_cloud.py --projects. Mocked tests only; live RLS unverified.
- Step 3: phone Projects tab + offline queue + sign-out clearing. 14/14 scripted checks pass at 390px
  light and dark against a local Supabase stand-in (online, offline queue, reopen offline, reconnect,
  no duplicates, sign-out warning and clearing). Not tested on a real phone. APK built 15:15:
  web\android\app\build\outputs\apk\debug\app-debug.apk (no secret keys in the bundle).
- Step 4: Android local reminders (off by default, generic text). Only the build is verified.
- Part 3: writeback.py (worktree on phone-review, allow-list, human cells only, checks, approvals in
  [writeback] write/push). 9 git-based tests pass. Dry run on scratch copies with the REAL checks:
  * pushback: test_evidence_provenance pins label CSV hashes in reports/run-provenance.json, so any
    write to an existing sheet fails its own tests. Only unpinned (new) sheets can be written.
  * nextword: test_committed_sheets_are_blank_and_match_the_generator requires committed sheets to
    stay blank, so filled verdicts fail its own tests on any branch.
  Both stops were correct (nothing committed). Owner decision needed before any real write.
- No real clone was written; copy holds 2 TEST answers, fixture home 1 — never write those back.
- Part 4 (LAN/Tailscale) and Part 5 not started. Pushes, SQL, migrations all wait on the owner.

## Update 2026-11-16 (evening) — Part 4 built, Part 5 partly done
- Part 4: [lan] network = "tailscale" (tailnet-only bind, *.ts.net name, tailscale cert), phone codes
  scoped to /api/phone/*, CORS for the app shell only, live-then-cloud phone mode, pairing and
  revoke on Projects. 7 mocked tests + 5 node tests. LAN mode itself is still NOT run (needs the
  owner's go-ahead: it opens a listener). Owner steps: docs/LAN_AND_PANEL.md §8.
- APK rebuilt 19:39 with live mode; scanned: no secret keys.
- Spacing measured: 390 (card) and 1440 (new sections) — no critical/serious findings.
- Backup of the live folder: D:\LocalAI\signaldesk-backup-before-project-coach-20261116 (SQLite online
  backup; row counts match; integrity ok). Live DB is schema 2; a scratch copy migrates to 7 with all
  rows and job statuses kept. The live folder itself is NOT migrated — waiting for the owner.
- Docs updated: README status table (PC rows), EVALUATION.md §5, PROJECT_COACH.md, LAN_AND_PANEL.md §8.
- Pushes: see the final report for which branches were pushed.

## Decisions waiting on the owner
1. Run cloud/project_coach.sql in Supabase; then verify_cloud.py --projects with two accounts.
2. Write-back: both repos' tests reject filled answers (pushback hash pins; NextWord blank sheets).
   Change those tests/manifest, write to a separate review file instead, or keep exports only?
3. pushback has untracked HANDOFF.md and reports/runs/ — write-back refuses until handled.
4. [coach] auto_prepare on? 5. Delete the TEST answers on the copy and fixture homes?
6. Go-ahead to run LAN/Tailscale mode after your setup steps. 7. Go-ahead to migrate the live folder.

## Update 2026-11-17
- Supabase SQL run by owner; verify_cloud.py --projects on the live project: 32/32 pass.
- Owner decisions applied: auto_prepare on by default (own loop step, works without cloud; checked
  on the copy and live); TEST answers, their export and scratch fixtures deleted; pushback write-back
  unchanged (only unpinned sheets); NextWord answers go to evals/local_ai/human_review_filled
  (dry run with its real checks: 145 tests + compare_review passed, 5 new files, kit unchanged).
- Live folder migrated with owner approval: config.toml created (3 projects; writeback off), schema
  2 -> 7, rows/statuses kept, integrity ok. Started once: Pipeline and Projects respond; today's batch
  prepared by itself. Backup: D:\LocalAI\signaldesk-backup-before-project-coach-20261116.
- Phone sync of tasks runs only when started with scripts\start-v2.ps1 (it loads delivery.env).
- Waiting on owner: Tailscale setup (docs/LAN_AND_PANEL.md §8), real-phone tests, and adding
  "nextword" to [writeback] write/push in D:\LocalAI\signaldesk\config.toml when ready.
- 2026-11-17 Tailscale live mode RUN on the live folder: listeners only 127.0.0.1:8780 and
  100.x:8443; trusted ts.net certificate; 11 probes from the laptop over the tailnet name all as
  intended (sign-in required, foreign origin/raw IP/plain HTTP refused, 8780 and 8000 unreachable on
  the tailnet address, HSTS); phone route returned phone-safe cards with a throwaway code that was
  then revoked. Waiting: owner pairs the Pixel 7 and runs the real-phone checklist.
