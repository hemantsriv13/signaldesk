# SignalDesk

[![CI](https://github.com/hemantsriv13/signaldesk/actions/workflows/ci.yml/badge.svg)](https://github.com/hemantsriv13/signaldesk/actions/workflows/ci.yml)

A personal job-search and AI-reading desk that runs on one Windows laptop. It:

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

**Four agents share one model.** An agent here is ordinary code with a bounded job, not an autonomous browser.

| Agent | Collects (no model) | Asks the model for |
|---|---|---|
| Job Scout | Public job-board APIs of the employers in Sources. Location class, pay wording (CTC, base or other kept apart), role family, review bucket, new/changed/no-longer-listed, duplicates. | Essential versus preferred requirements with quotes, profile evidence (cited by fact id), gaps, unknowns, a match label. No percentages. |
| Reading Scout | RSS/Atom feeds. Full text, excerpt or title only; syndicated repeats are linked, not counted twice. | Main argument, evidence with quotes, why it may matter, limits, one concept. |
| Case Study Analyst | Full-text articles that describe a deployment, or a public URL you paste. | Problem owner, workflow, bottleneck, AI's part, ordinary software's part, data, failure modes, impact evidence, lesson, experiment. Each point is labelled source fact, vendor claim, inference or missing. |
| Digest Editor | Up to 3 jobs, 1 case study, 2 articles and 1 term, none repeated from recent briefings. Rechecks a chosen job's board if it wasn't verified in the last 12 hours. | One suggested action, which must point at a briefing item. If the model is unavailable, a fixed rule writes it and the briefing says so. |

The queue sends one model request at a time and survives restarts. A failing task is retried up to 3
times, with less text each time. If the model server is down or serving another model, tasks wait
without spending attempts. Results are cached by content, prompt version, model, text budget and
profile version; change any of these and the item is analysed again on the next run.

## What is verified

[docs/STATUS.md](docs/STATUS.md) lists every feature as **verified** (with the record of how it was
checked) or **experimental** (with the commands that would verify it). In short:

- Verified on real runs: job boards and feeds, the rules, the model queue and its analyses, briefings,
  the desktop interface, CV matching, cloud sync and the Android reader.
- Not yet done: **your own review of the job-fit judgements** ([HUMAN_REVIEW.md](docs/HUMAN_REVIEW.md))
  and the 9B model comparison.
- Experimental and **off by default**: Wellfound/YC import, investor announcement pages, role families
  from duties, contacts and drafts, the 08:00/20:00 schedule and Windows task, larger-model escalation,
  LAN mode and the Edge side panel. Each needs a switch in `config.toml` (`[experimental]`), and the
  app labels it "Experimental: not yet validated".

Tests: 242 mocked tests pass (plus 2 recorded known failures in contact discovery; see STATUS.md), and
the deterministic evaluation passes all 19 hand-written cases. CI runs both, and the web checks, on every push.

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
