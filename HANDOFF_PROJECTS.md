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
