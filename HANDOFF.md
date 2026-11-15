# Handoff (updated 2026-11-15, end of phase 3)

Branch `v4-outcomes`, based on `cleanup/verified-core` (neither merged or pushed). Work only on the
data copy `D:\LocalAI\signaldesk-v4-copy` (no delivery.env, port 8792, V3 switches on in its config.toml).
Live data `D:\LocalAI\signaldesk` is untouched. Tests: 292 passed, 0 known failures.

## Done
- Phase 1 (V3 validation on the copy): record in docs/V3_VALIDATION.md. Fixed: BOM in config.toml,
  second process breaking a live sweep, US states classed "uncertain".
- Decision applied: roles placed only by the model go to To review, not Matches.
- Phase 2: pipeline on jobs.status + job_events (migration 3), Pipeline page, Today's actions (rules
  only), Application form on a job; old status select only before Shortlisted.
- Phase 3: team-page contact discovery fixed (link-to-person by page element, names with initials,
  home-page redirects, customer quotes, job-board hosts). Drafts quote one posting sentence and use at
  most two profile facts; claims about you must map to a fact; drafts claiming the role/company are
  rejected. Mark sent with date, day-5/day-12 follow-ups (migration 4), LinkedIn URL entry.

## Unverified
- Contact discovery: owner has NOT reviewed the 10-role results; do not mark it working.
- Mark sent and follow-ups: fixture tests only, not used on the copy. New UI: not checked in browser.
- Spacing never measured; dashboard review skipped by owner.
- Wellfound import, Windows schedule task, larger-model escalation: not run.
- Model drafts: 0 of 11 accepted by the checks on real roles (4B).

## Open decisions (owner)
1. Verdict on the 10-role contacts and drafts.
2. Delete the 2 wrong Stripe contacts (customer quotes from 13 Nov) on the copy? Ask first.
3. Stop model drafts (template only) or keep for the 9B comparison in phase 5?
4. Start phase 4 (gaps and what to lead with).

## Remaining phases (from the brief)
- 4: aggregate gaps/essential requirements in target families; lead-with suggestions from existing
  facts (accept/reject); link gaps to reading queue.
- 5: measure 4B at 4096/8192 context (no config change); 4B vs 9B via eval.run_eval compare (ask
  before switching model); overnight batch mode design only, show before building.
- Housekeeping: three .patch files (confirm applied, ask before removing); README status table V1-V4
  with test count and placeholders; fill docs/EVALUATION.md, list outputs for human review.

## Resume
```bat
cd C:\Users\Hemant\Documents\GitHub\signaldesk
git checkout v4-outcomes
.venv\Scripts\python -m pytest -q
C:\Users\Hemant\Documents\GitHub\local-ai\start-colibri.cmd 4b
.venv\Scripts\python -m signaldesk --home D:\LocalAI\signaldesk-v4-copy
:: then http://127.0.0.1:8792 ; stop Colibri with local-ai\colibri\coli.cmd stop
```
Rules from the owner: small commits, no push, ask before deleting anything, model switch, scheduled
task, firewall/LAN; reports at most 15 lines; no browser checks unless asked.
