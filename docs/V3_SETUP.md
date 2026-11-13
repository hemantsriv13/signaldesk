# SignalDesk V3: wider job discovery, funded startups, contacts and twice-daily sweeps

Status: implemented in code, **not run**. Nothing below has been executed by the person or agent
that wrote it: no build, test, evaluation, server, sweep, schedule install or model call. Treat every
feature as unverified until you have run the checks in "Validate" yourself.

## What it answers

1. **Worth applying to today**: Today shows open Bengaluru or India-remote roles in your role
   families, each with the deciding line from the posting, one point from your profile, the main gap,
   pay against your target and freshness, plus an Apply link.
2. **Funded startups to watch**: a new Funded startups page shows India-linked startups with a dated
   funding announcement (30/90/180 days), whether their careers page lists matching roles, and a
   separate watchlist for portfolio companies with no dated round.
3. **Who to contact**: Outreach shows up to three people per shortlisted role, why each was chosen,
   where they were verified, and a draft note and message to copy.

## Sources and what each can do

| Source | Mode | What it does | What it needs |
|---|---|---|---|
| Employer boards (Greenhouse, Lever, Ashby) | Automatic | Final job records and Apply links; closes listings only when its own board stops listing them | Nothing new |
| Wellfound | Import-assisted | Wellfound does not allow automated collection. Paste saved listing URLs, a CSV export or JSON under Sources → Discovery sources → Wellfound → Import saved listings. Each listing is matched to the employer's board; unmatched ones stay "Not yet on employer's board" | Your saved listings. A URL alone is stored only once you add title and company columns |
| YC startup jobs (ycombinator.com/jobs) | Automatic | Adds employer ATS boards it links; other listings are kept as unverified until the employer's board confirms them | Nothing; if YC needs scripts to render, it shows "Temporarily unavailable" with the reason |
| YC companies in India | Automatic | Portfolio membership only: watchlist entries with their website. A YC batch is never a funding date | Nothing |
| WestBridge Capital | Needs setup | Reads dated announcements, extracts company, round and amount, resolves the website from links in the announcement | The address of WestBridge's news/announcements page (not confirmed during implementation, so left empty) |
| Accel, Peak XV/Surge, Lightspeed | Off, needs setup | Same as WestBridge | A public news or announcement page address each |
| Any other investor or job board | Configuration | Add `[[source]]` entries; see `docs/sources.example.toml` | A public page address |
| LinkedIn | Not integrated | No supported people-search or messaging API is available to this project. LinkedIn search links on Sources open your browser; contact discovery uses public pages instead | n/a |

## How recency and evidence work

- A funding date is the announcement's own publication date (JSON-LD `datePublished`, article meta, or
  the date printed beside the link). Never the YC batch, an "updated" date or the day SignalDesk found it.
- "Recently funded" defaults to 180 days, with 30/90/180 tabs. Undated companies sit in the watchlist.
- Syndicated reports of the same round (same company, same round label or amount, within 45 days)
  count once and list the other reports. A different round at the same company is kept separately.
- India-based needs a stated location ("Bengaluru-based", "headquartered in India"); overseas companies
  with open roles located in India are "hiring in India"; anything else is "India link not confirmed".
- Funding recency is shown beside a job but never added to its ranking.

## Matching

- Locations: Bengaluru (all spellings, explicitly Bengaluru-based hybrid), Remote open to India,
  Uncertain (Remote with no country, generic India, unstated) and Elsewhere. Uncertain roles stay in
  To review, never in top matches.
- Role families, several per job: Founder's office and chief of staff; Strategy and business
  operations (now its own family, switched on for you automatically if founder's office was on); AI
  product and evaluations. Titles and duties both count: "Special Projects" reporting to the founder
  qualifies; a sales role mentioning account strategy, or an assistant managing a calendar, does not.
  Unclear titles get one look from the local model, only when the location already qualifies.
- Pay: Confirmed above target, Range overlaps target, Below target, or Pay unknown. Base and CTC stay
  apart: a base below target is "unknown", not "below". Undisclosed pay never excludes a role.
- Your background lives only in your profile (Profile and settings), which is outside Git. Make sure it
  states your AB InBev work, BrewHub and your tools as facts, and lists under "Things you do not claim"
  that you have not held a PM or Chief of Staff title and have no production ML experience. Drafts and
  fit analyses may only cite those facts.

## Contacts and outreach

- People come from the posting itself, the company's own team/about page, the funding announcement,
  or your own entry. A profile link is stored only when that page links it beside the name. Nobody is
  matched on name alone; people without evidence are listed as "Not verified" and get no draft.
- Drafts: a template draft is created immediately (works with Colibri off); the local model may
  replace it with a checked draft (company named, your cited fact used, no generic praise, no claimed
  titles). Copy note, Show full message, Copy message, Open profile, Mark contacted.
- Sending: no authorised messaging integration exists, so automatic sending is unavailable and the
  switch is disabled. The send path (selected roles only, daily cap, one message per person across roles,
  stop switch, "send unclear" never retried) is implemented and tested with a fake sender only.

## Runs, schedule and lock

- One entry point for everything: Run now (Today, with a scope: everything, jobs, funding, contacts,
  reading, or one source), the in-app schedule, and the Windows task all call the same sweep, and share
  one lock that also works across processes. A second trigger reports the sweep already running.
- Order in a full sweep: Funding Scout → Job Scout (boards and listing sources) → analyses → Contact
  Scout → briefing.
- Each source fails on its own; nothing is closed because a source failed or stopped part-way;
  unprocessed announcements stay pending for the next sweep. Today and Sources show "Worked 2 h ago"
  versus "Failing since …" so nothing-new and broken look different.
- The in-app schedule defaults to 08:00 and 20:00 IST (Profile and settings → Schedule), only while the
  app is open. The opt-in Windows task runs while the app is closed; the PC must be on and you logged in.

## Local model

- Colibri only. No hosted model, paid LLM or paid search. Model calls: unclear roles, fit analysis,
  unreadable announcements, outreach drafts. Location, pay, dates, dedupe and scheduling are code.
- `concurrency = 1` by default. Exact repeated work is cached by content, task, model, prompt version
  and profile version; a changed posting, location, recipient or profile makes the result stale.
- Optional larger model: set `escalation_model_id` (and `escalation_base_url` if it runs on another
  port) in `<data dir>\config.toml` to the exact id Colibri reports. It is asked only when the default
  answer fails checks or stays unsure, and its answer must pass the same checks. With Colibri serving one
  model at a time, escalation only happens when the larger model is reachable.

## Validate (run these yourself)

From `C:\Users\Hemant\Documents\GitHub\signaldesk` in PowerShell:

```powershell
# 1. Offline checks (synthetic fixtures; no network, no model)
.venv\Scripts\python -m pytest tests\test_v3.py -q
.venv\Scripts\python -m pytest -q
.venv\Scripts\python -m eval.run_eval rules

# 2. Build the web app (type check + bundle)
cd web; npm run build; cd ..

# 3. Restart SignalDesk on the new code (stop the running one first), with cloud settings
powershell -File scripts\start-v2.ps1

# 4. First manual sweeps from the command line (or use Run now on Today)
.venv\Scripts\python -m signaldesk sweep --scope funding
.venv\Scripts\python -m signaldesk sweep

# 5. Optional Windows schedule (08:00 and 20:00; add -StartModel to start Colibri 4B first)
powershell -ExecutionPolicy Bypass -File scripts\schedule-install.ps1
Get-ScheduledTask -TaskPath '\SignalDesk\'
Start-ScheduledTask -TaskPath '\SignalDesk\' -TaskName 'SignalDesk sweep 0800'   # try one now
powershell -ExecutionPolicy Bypass -File scripts\schedule-remove.ps1               # remove

# 6. Compare the installed model with a larger one on identical examples
.venv\Scripts\python -m eval.run_eval replay --label small
#    switch Colibri to the larger model, then (use the id the server reports):
.venv\Scripts\python -m eval.run_eval replay --label large --model-id YOUR_LARGER_MODEL_ID
.venv\Scripts\python -m eval.run_eval replay-report D:\LocalAI\signaldesk\evals\replay-small-....json D:\LocalAI\signaldesk\evals\replay-large-....json
```

## UI checklist

- Today: Run now with a scope; "Last refresh" line with counts and next scheduled time; three panels
  (Worth applying to today with Apply, Recently funded, Ready to contact); Sources details control.
- Jobs: filters for Location (Bengaluru / Remote, open to India / Uncertain / Elsewhere), Role family
  and Pay against your target; each card shows location, families, freshness, pay band and
  "Not yet on employer's board" when unverified; detail shows duties, Found on, Funding and Who to contact.
- Funded startups: 30/90/180/Watchlist tabs, India filter, opening state that separates "no matching
  opening" from "could not check", Add a startup.
- Outreach: Ready to send / Contacted / Sent / Needs a look; Copy note, Mark contacted; Automatic
  sending shown as not available.
- Sources: Discovery sources with modes, page address fields and the Wellfound import box.
- Profile and settings: Schedule takes a list of times; Local model shows requests at once and the
  larger model's status.
