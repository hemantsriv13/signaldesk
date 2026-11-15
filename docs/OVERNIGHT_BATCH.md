# Overnight batch mode: design (not built)

Status: proposal for the owner to approve. Nothing here exists in code yet.

## What it does
One command queues everything that waits on the local model and runs it unattended, one request at a
time, then writes a morning summary.

```bat
.venv\Scripts\python -m signaldesk batch --until 07:30 [--scope all|fit|drafts|gaps] [--home DIR]
```

## What it queues, in this order
1. Job-fit analyses that are missing or outdated for open matches and To review roles (no per-run
   limit of 12; the night is the budget).
2. Role checks for unclear titles (still To review only, never straight to Matches).
3. Reading cards for unread full-text articles; case studies for candidates.
4. Outreach drafts for shortlisted roles whose drafts are templates (only if the owner keeps model
   drafts; on real roles the 4B passed 0 of 11).
5. Gap aggregation (rules only, after the analyses finish), so the Skill gaps page is current.

No collection by default: fetching runs only with `--sweep`, so a night run never depends on websites.

## How it runs
- Reuses the existing queue and worker, the sweep lock and the cache keys: nothing is analysed twice,
  and a sweep from the app or the scheduled task cannot overlap it.
- Stops at `--until` or when the queue is empty. A request in progress finishes; the rest stay queued.
- If Colibri is down or serving another model, tasks wait without spending attempts (existing
  behaviour); the summary says so instead of reporting failures.
- Optional `--start-model` uses the existing launcher check (only if port 8000 is free).
- Started by hand or by the existing opt-in Windows task (still needs the owner's approval to install).

## Morning summary
`<data dir>\digests\night-YYYY-MM-DD.md`, plus a line on Today:
- per kind: queued, done, cached, failed (with the first error), still waiting;
- model time, requests, tokens as reported by Colibri;
- what changed for the job search: new potential matches, roles moved to To review, new drafts,
  follow-ups due today, top 3 recurring gaps;
- anything that needs the owner: failed tasks, model unavailable, lock held by another process.

## Safety
No sending, no syncing (cloud copies stay a separate step), no new sources. Same validation as every
other model output. The summary contains titles and counts, never profile text or contact details.

## Open questions for the owner
- Start time and `--until` default (proposed 01:00 to 07:30).
- Include collection (`--sweep`) at the start of the night, or keep fetching to daytime sweeps?
- Keep model drafts in the batch, or templates only?

## Estimate
About half a day: a `batch` subcommand on top of `sweep.run_headless`, a queue-filling function per
kind, the summary writer, and tests with the fake model.
