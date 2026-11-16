# SignalDesk

[![CI](https://github.com/hemantsriv13/signaldesk/actions/workflows/ci.yml/badge.svg)](https://github.com/hemantsriv13/signaldesk/actions/workflows/ci.yml)

A personal job-search and AI-reading desk that runs on one Windows laptop.

## What this does for a job search

Each day it finds open Bengaluru and India-remote roles on employers' own boards, says which ones fit
your profile and why, and lists at most five concrete actions: reply, follow up, send a drafted note,
apply to a shortlisted role, or decide on a new match. The Pipeline page tracks every application.

| Since you started | Number |
|---|---|
| Roles shortlisted | _fill in_ |
| Applications sent | _fill in_ |
| People contacted | _fill in_ |
| Replies | _fill in_ |
| Interviews | _fill in_ |
| Offers | _fill in_ |

## In short

It:

- finds relevant jobs on employers' own job boards, so you apply on their sites;
- follows selected Substack newsletters and AI engineering blogs;
- takes real AI case studies apart: problem, workflow, what AI does, evidence;
- writes a short briefing that links jobs, reading and one next action.

**The local core** does all collection, rules and analysis on this laptop. Language work goes to a local
model through Colibri. No paid model API is used and there is no cloud model fallback.

**Optional parts**, each off until you set it up:
- a private cloud reader: finished briefings sync to your own Supabase project ([V2_SETUP.md](docs/V2_SETUP.md));
  start with `powershell -File scripts\start-v2.ps1`, because `scripts\start.cmd` does not load the cloud settings;
- an Android app that reads those copies, even with the laptop off.

<!-- Screenshots: add images taken with `python -m signaldesk --demo` here. -->

## How it works

```
 Sources ──► collection (code) ──► rules (code) ──► persistent queue ──► local model (one request at a time)
   │          Greenhouse/Lever/Ashby   location class      SQLite tasks           │
   │          RSS/Atom feeds           pay wording         cache keys             ▼
   │          manual URLs (robots.txt) role family        retries/backoff   validation (code): quotes must be in the
   │                                   review bucket       cancel/resume     source, claims must cite profile facts,
   ▼                                                                         labels from fixed lists, "unknown" allowed
 SQLite: jobs (+versions), articles, analyses, runs, tasks, model_calls, briefings, feedback
   ▼
 FastAPI on 127.0.0.1:8780 ──► React web app (list/detail views, light and dark)
```

**Five core agents.** An agent here is ordinary code with a bounded job, not an autonomous browser.

| Agent | Collects (no model) | Asks the model for |
|---|---|---|
| Job Scout | Public job-board APIs of the employers in Sources. Location class, pay wording (CTC, base or other kept apart), role family, review bucket, new/changed/no-longer-listed, duplicates. | Essential versus preferred requirements with quotes, profile evidence (cited by fact id), gaps, unknowns, a match label. No percentages. |
| Reading Scout | RSS/Atom feeds. Full text, excerpt or title only; syndicated repeats are linked, not counted twice. | Main argument, evidence with quotes, why it may matter, limits, one concept. |
| Case Study Analyst | Full-text articles that describe a deployment, or a public URL you paste. | Problem owner, workflow, bottleneck, AI's part, ordinary software's part, data, failure modes, impact evidence, lesson, experiment. Each point is labelled source fact, vendor claim, inference or missing. |
| Digest Editor | Up to 3 jobs, 1 case study, 2 articles and 1 term, none repeated from recent briefings. Rechecks a chosen job's board if it wasn't verified in the last 12 hours. | One suggested action, which must point at a briefing item. If the model is unavailable, a fixed rule writes it and the briefing says so. |
| Project Coach | Read-only Git metadata and outstanding human reviews from configured local projects. Persists up to 3 reviews and 3 laptop reminders each day. | Nothing: rules select tasks and templates explain them. Your verdicts stay in SignalDesk until exported to its data folder. |

The queue sends one model request at a time and survives restarts. A failing task is retried up to 3
times, with less text each time. If the model server is down or serving another model, tasks wait
without spending attempts. Results are cached by content, prompt version, model, text budget and
profile version; change any of these and the item is analysed again on the next run.

## What is verified

Verified means it was run for real and the result recorded; the last column says how. Details and the
commands that would verify the rest: [docs/STATUS.md](docs/STATUS.md).

| Version | Feature | Status | How it was checked |
|---|---|---|---|
| V1 | Job boards, feeds, rules, model queue, fit analyses, briefings | Verified | Live runs 2026-11-02 ([EVALUATION.md](docs/EVALUATION.md) §2) |
| V1 | Your review of the job-fit judgements | Not done | Kit ready ([HUMAN_REVIEW.md](docs/HUMAN_REVIEW.md)) |
| V2 | Desktop interface, careers-page discovery, CV matching | Verified | Real pages and a real model run ([V2_VALIDATION.md](docs/V2_VALIDATION.md)) |
| V2 | Cloud reader and Android app (optional) | Verified | `verify_cloud.py` on the live project; owner on a real phone |
| V3 | Hiring companies, YC India and WestBridge portfolios | Verified | Runs on a copy of the data ([V3_VALIDATION.md](docs/V3_VALIDATION.md)) |
| V3 | Location groups, Run now and the shared lock | Verified | Runs on a copy of the data, after fixes (V3_VALIDATION.md) |
| V3 | Role families from duties | Experimental, off | Ran on a copy: about half the model's placements were wrong; model-placed roles now go to To review |
| V3 | YC jobs, Wellfound import, investor announcements | Experimental, off | YC: engineering roles only, parser faults. Wellfound and announcements: not run |
| V3 | Pay bands | Experimental | Ran on a copy, but only USD pay was disclosed, so INR bands are unchecked |
| V3 | Contacts and drafts | Experimental, off | 10 real roles: people found for 4, not yet reviewed by you; drafts are templates (local models passed 0 of 22) |
| V3 | Schedule and Windows task, escalation, LAN mode, side panel | Experimental, off | Not run |
| V4 | Pipeline, Today's actions, stage form, Mark sent, follow-ups | Built, tested | 295 mocked tests; pipeline ran on demo data in the browser; Mark sent and follow-ups not used on real data |
| V4 | Skill gaps and Lead with | Built, tested | Mocked tests; grouping ran on the copy (25 roles); not checked in browser |
| V4 | Demo mode (`--demo`) | Verified offline | `tests/test_demo.py`: no network or model requests |
| PC | Project Coach: daily batch, sourced reasons, desktop Projects page, exports | Verified on a copy | Ran on the data copy against the real clones 2026-11-16; one answer of each type in the browser (label type on a scratch copy, real pushback has none open); exports opened; 390/1440/1728, light and dark |
| PC | Grader verdicts hidden from label tasks | Verified | Tests on API and stored tasks, plus a scan of the live API response and rendered page |
| PC | Cloud copy of tasks and phone answers | Built, mocked | Mocked tests only; `cloud/project_coach.sql` not yet run on the live project, so row-level security is unchecked |
| PC | Phone Projects tab, offline queue, sign-out clearing | Built, scripted | 14 scripted checks in headless Chrome at 390 px against a local Supabase stand-in; APK built; not yet on a real phone |
| PC | Daily phone reminders | Built | APK builds with the plugin; not tested on a phone |
| PC | Write answers into project clones (phone-review) | Built, blocked | Git tests on throwaway repos; dry run with the real repo checks: both repos' own tests reject filled answers in their current sheets, so it stops before committing |
| PC | Live phone access over Tailscale | Built, mocked | Mocked tests (tailnet-only bind, token scope, CORS, revocation); no tunnel or phone run yet |

Tests: 343 mocked tests and 13 phone-app tests pass, and the deterministic evaluation passes all 19 cases. CI runs both, and
the web checks, on every push.

## Quick start (Windows)

Requirements: Python 3.12, Node 20 or later, and (optionally) the Colibri model server.

```bat
cd <your GitHub folder>\signaldesk
scripts\setup.cmd                          :: once: Python env, packages, web build
.venv\Scripts\python -m signaldesk --demo  :: try it on invented data: nothing is fetched, no model is called
scripts\start.cmd                          :: your own desk on http://127.0.0.1:8780
```

`--demo` builds a throwaway database from the test fixtures in a temporary folder and never reads your
data folder. Use it for screenshots, or to show someone the app.

Your data lives outside Git in `D:\LocalAI\signaldesk` (or `%SIGNALDESK_HOME%`, or `--home`): the
database, `profile.json` (your facts; fit analysis can cite only these), `config.toml` (see
`config.example.toml`), logs, briefings and evaluation outputs. `scripts\start.cmd` asks Colibri to
load the 4B model if port 8000 is free; see [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) for the model
start-up options and common problems.

```bat
scripts\test.cmd                                 :: mocked tests + deterministic eval + type check
.venv\Scripts\python -m eval.review export       :: a sheet for your review of job-fit analyses
```

## Safety rules built in

Project Coach's laptop-only Projects page is documented in [PROJECT_COACH.md](docs/PROJECT_COACH.md).
Configure `[[project]]` entries from `config.example.toml`, then prepare a daily batch on that page.
The CLI requires an explicit data home: `python -m signaldesk.projects collect|export|writeback --home <home>`.
Writing answers into a clone needs your approval per repo in `[writeback]`, works on a `phone-review`
branch in a separate worktree, changes only human columns in allow-listed review files, and never
touches main. The phone can answer through the cloud copy, or live over Tailscale (LAN_AND_PANEL.md §8).

- **This computer only, by default.** The app binds to 127.0.0.1, refuses other Host names, and
  accepts changes only from its own pages. Optional LAN mode (experimental, off) adds one signed-in
  HTTPS address and refuses to start without a password, a trusted certificate and a private address.
- **Safe fetching.** Fetched URLs must be http(s) on ports 80/443 and resolve to public addresses.
  Redirects are rechecked at every hop. Responses are size-capped, timed out and paced per host.
  (Known limit: DNS rebinding between check and connect is not caught.)
- **Retrieved text is data, never instructions.** It is sent to the model inside delimiters. Wording
  aimed at AI tools is flagged. Model output can't change preferences, run commands or send anything.
- **Private data stays out of Git and logs.** Profile, database, caches, logs, review sheets and model
  files are never committed. Emails, phone numbers and keys are redacted from the log file. Cloud
  copies hold finished briefings only: never contacts, drafts, profile facts or full articles.

## Limitations

- **The context window is small.** With 2,048 tokens, a request carries about 6,000 characters. Long
  job descriptions are cut to their summary and requirement sections, and long articles to their
  opening. The UI says how much was read.
- **The 4B model can still be wrong** even after validation: a quote can be real but misread. Quotes are
  checked, judgements aren't, and nobody has reviewed them yet. Open the original before acting.
- **"Potential match" is not confirmed eligibility.** Remote roles without an India statement stay in To review.
- **Coverage is limited.** Only employers in Sources are covered ([SOURCES.md](docs/SOURCES.md)). No
  LinkedIn scraping, logged-in browsing or paywall workarounds; boards without a public API need manual entry.
- **Nothing runs while the laptop is off.** New briefings need the laptop and Colibri running; the cloud
  reader shows only what was already synced. Supabase's free plan can pause an idle project.

## More

[CV matching](docs/CV_MATCHING.md) · [Evaluation record](docs/EVALUATION.md) ·
[V2 and V3 release notes](docs/RELEASES.md) · [V3 setup](docs/V3_SETUP.md) ·
[LAN and side panel](docs/LAN_AND_PANEL.md) · Licence: [MIT](LICENSE)
