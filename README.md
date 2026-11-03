# SignalDesk

A personal job-search and AI-industry research desk that runs on one Windows laptop. It:

- finds relevant jobs on employers' own job boards, so you can apply on their sites;
- follows selected Substack newsletters and AI engineering blogs;
- takes real AI case studies apart: problem, workflow, what AI does, evidence;
- writes a short briefing that links jobs, reading and one next action.

Language work is done by a local model through Colibri. There are no paid model APIs, no paid scraping services and no cloud fallback.

## Quick start (Windows)

```bat
cd <your GitHub folder>\signaldesk
scripts\setup.cmd        :: once: Python env, packages, web build
scripts\start.cmd        :: starts http://127.0.0.1:8780 and opens it
```

Requirements: Python 3.12, Node 20 or later, and (optionally) the Colibri model server.

### Local model

SignalDesk talks to any OpenAI-compatible server at `http://127.0.0.1:8000/v1` and expects the model `qwen3-4b-instruct-2507-q4km`. On Windows, `scripts\start.cmd` now requests startup of the existing sibling `local-ai\start-colibri.cmd` with `4b` when port 8000 is free. No models are downloaded. Keep the model window open; the app may briefly show offline while loading, then its normal health checks detect readiness.

If port 8000 is occupied, the launcher does not invoke Colibri's restart script—even if the running service serves the wrong model. Custom model IDs/endpoints are also left alone. Avoid starting multiple apps' model launchers simultaneously.

Use `scripts\start.cmd --no-start-model` for app-only startup. If your launcher is elsewhere, use `scripts\start.cmd --model-launcher "C:\path\to\start-colibri.cmd"`. Direct `python -m signaldesk` remains app-only unless you add `--start-model`.

For manual startup, run from the **GitHub folder**, not from this repo:

```bat
cd <your GitHub folder>
local-ai\start-colibri.cmd 4b
```

That script stops any running Colibri first, so only one model is ever loaded. NextWord uses the same server and model; both apps can share it. Without the model, collection, browsing and briefings still work. Analysis waits and is marked pending.

## Where things live

| What | Where | In Git? |
|---|---|---|
| Code, tests, evaluation cases | this repo | yes |
| Database, profile, preferences, logs, briefings, eval results | `D:\LocalAI\signaldesk` (or `%SIGNALDESK_HOME%`, or `--home`) | no |
| Configuration | `<data dir>\config.toml`; see `config.example.toml` | no |
| Model files | `D:\LocalAI\models` (Colibri's; SignalDesk reuses them) | no |

Your profile is `profile.json` in the data folder (shape: `profile.example.json`). Edit it in **Profile and settings**. Fit analysis can cite only the facts in it.

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

**Four agents share one model.** An agent here is ordinary code with a bounded job. It is not an autonomous browser.

| Agent | Collects (no model) | Asks the model for |
|---|---|---|
| Job Scout | Public job-board APIs of the employers in Sources. Location class, pay wording (CTC, base or other kept apart), role family, review bucket, new/changed/no-longer-listed, duplicates. | Essential versus preferred requirements with quotes, profile evidence (cited by fact id), gaps, unknowns, a match label. No percentages. |
| Reading Scout | RSS/Atom feeds. Full text, excerpt or title only; syndicated repeats are linked, not counted twice. | Main argument, evidence with quotes, why it may matter, limits, one concept. |
| Case Study Analyst | Full-text articles that describe a deployment, or a public URL you paste. | Problem owner, workflow, bottleneck, AI's part, ordinary software's part, data, failure modes, impact evidence, lesson, experiment. Each point is labelled source fact, vendor claim, inference or missing. |
| Digest Editor | Up to 3 jobs, 1 case study, 2 articles and 1 term, none repeated from recent briefings. Rechecks each chosen job's board if it wasn't verified in the last 12 hours. | One suggested action, which must point at a briefing item. If the model is unavailable, a fixed rule writes it and the briefing says so. |

**Queue.**
- One model request at a time.
- Tasks survive restarts: an interrupted task is put back in the queue.
- A failing task is retried up to 3 times with backoff and sends less text each time; then it is marked failed and the queue moves on.
- If the server is down or serving another model, tasks wait without spending attempts.
- Cancel stops queued tasks. A request already in progress finishes first.
- The cache key combines:
  - the item's content hash;
  - the prompt version;
  - the model id;
  - the text budget;
  - the profile version (for job fit) or reading interests (for cards).

  Changing any of these marks old results outdated, and the item is analysed again on the next run.

**Usage shown (Agent runs).**
- Items fetched and analysed, cache hits, model requests and failures.
- Model time, retries and errors.
- Token counts only where the server reported them.

Paid APIs are disabled because none exist in the code. No money or electricity figures are estimated.

**Scheduling.** Off by default. When turned on in Settings, SignalDesk runs every agent daily at a set time (Asia/Kolkata):
- It runs only while the app is running.
- If the app was off at the scheduled time, it catches up once when it next starts.
- A run already in progress means that slot is skipped.
- Nothing is added to Windows startup.

## Source coverage (checked 2026-11-02)

**Employers, enabled.** Each board is tied to the employer: the careers page links to the board or calls its API, or the job links are on the employer's own domain.
- Anthropic, Databricks, Glean, Sarvam AI, Observe.AI, Stripe, MongoDB, Elastic.
- Groww, CRED, Cursor (Anysphere), SpotDraft, UiPath, Fivetran, Together AI.

**Employers, disabled until you confirm them.** Each board answered, but an automated check could not tie it to the employer:
- OpenAI, Atlan, ElevenLabs, Harvey, GitLab, Celonis, Meesho.

**Feeds, enabled.**
- Substack: Latent Space, Lenny's Newsletter, One Useful Thing, AI as Normal Technology, Interconnects, Ahead of AI, The Pragmatic Engineer.
- Blogs: Eugene Yan, Hamel Husain, Simon Willison, Chip Huyen.
- Engineering: Netflix TechBlog, Airbnb Tech Blog, Flipkart Tech Blog.

**Feeds, off by default.** Exponential View, OpenAI News (vendor, summaries only) and Hugging Face Blog (titles only).

**Not supported.**
- LinkedIn scraping, logged-in browsing, CAPTCHA solving and paywall workarounds.
- Workday, SmartRecruiters and other boards without a documented public API: mark those employers "manual" and add jobs by hand. A pasted URL is fetched only if robots.txt allows it, and schema.org JobPosting data is used when the page has it.

## Safety rules built in

- **Localhost only.** The server binds to 127.0.0.1 and refuses other hosts. Requests must name this machine, and changes must come from its own pages, so other websites can't drive the API.
- **Safe fetching.** Fetched URLs must be http(s) on ports 80/443 and resolve to public addresses. Redirects are rechecked at every hop. Responses are size-capped, timed out and paced per host. (Known limit: DNS rebinding between check and connect is not caught.)
- **Retrieved text is data, never instructions.** It is sent to the model inside delimiters. Wording aimed at AI tools is flagged in the UI. Model output can't change preferences, run commands or send anything. Preferences change only when you apply a suggestion.
- **Private data stays out of Git and logs.** Profile, database, caches, logs and model files are never committed. Emails and phone numbers are redacted from the log file.

## Tests and evaluation

```bat
scripts\test.cmd                                 :: mocked tests + deterministic eval + type check
.venv\Scripts\python scripts\live_check.py       :: live, read-only: every enabled source once, and the model server
.venv\Scripts\python -m eval.run_eval model      :: run prompts on fixtures and saved items with the served model
```

- **Mocked tests** (`tests/`, 69): no network and no model. They cover:
  - URL safety, rules and evaluation cases;
  - new, changed and closed jobs, failed and suspicious fetches, duplicates;
  - excerpts and repeated stories;
  - the queue: caching, invalidation, retries, waiting for the model, resume, cancel;
  - injection containment, scheduling decisions, API guards, quiet-day briefings.
- **Evaluation cases** (`eval/cases.json`) are hand-written fixtures you can read directly. They cover:
  - Bengaluru versus other locations, and remote roles with and without India eligibility;
  - missing pay, and CTC versus base;
  - required versus preferred requirements, and unsupported experience claims;
  - full articles versus excerpts;
  - vendor claims, and instructions embedded in content.
- **Live verification** is separate. See [docs/EVALUATION.md](docs/EVALUATION.md) for what was run on 2026-11-02.

### Comparing models (4B and the installed 9B)

`eval.run_eval model` runs against whichever model the server is serving, refuses if that isn't the model you name, and saves raw outputs plus automatic checks to `<data dir>\evals`. Switching to 9B stops the 4B server, and with it NextWord's tutor, so do it when nothing else needs the model:

```bat
cd <your GitHub folder> && local-ai\start-colibri.cmd 9b
cd signaldesk && .venv\Scripts\python -m eval.run_eval model --model-id qwen3.5-9b-q4km
.venv\Scripts\python -m eval.run_eval compare D:\LocalAI\signaldesk\evals\model-qwen3-4b-...json D:\LocalAI\signaldesk\evals\model-qwen3.5-9b-...json
cd .. && local-ai\start-colibri.cmd 4b
```

The comparison report has an empty **Human review** column. Automatic checks test format and rules, not which model is better.

## Limitations

- **The context window is small.** With 2,048 tokens, a request carries about 6,000 characters. Long job descriptions are cut to their summary and requirement sections, and long articles to their opening. The UI says how much was read.
- **The 4B model can still be wrong** even after validation: a quote can be real but misread. Quotes are checked, judgements aren't. Open the original before acting.
- **"Potential match" is not confirmed eligibility.** Remote roles without an India statement stay in To review.
- **Coverage is limited.** Only employers in Sources are covered. Big boards (Databricks, Stripe and others) contribute thousands of listings; the rules keep only matching roles for analysis.
- **Nothing runs while the laptop is off.** There is no system startup task.

## Troubleshooting

| Symptom | Check |
|---|---|
| "Model offline" | Is Colibri running? `curl http://127.0.0.1:8000/v1/models`. Start it with `local-ai\start-colibri.cmd 4b` from the GitHub folder. |
| "Different model running" | Colibri is serving another model (e.g. 9B). Restart it with `4b`, or change `model_id` in `config.toml` deliberately. |
| A source keeps failing | Run `scripts\live_check.py`. A 404 usually means the employer moved boards: edit it in Sources. Failed sources never close jobs. |
| Blank page | Run `scripts\setup.cmd` to build the web app, then restart. |
| Analyses all "outdated" | Your profile, the prompt version or `prompt_char_budget` changed. Run again, or Regenerate on Today. |
| Port in use | `scripts\start.cmd --port 8781` |
