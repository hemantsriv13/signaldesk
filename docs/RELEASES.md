# V2 and V3: what each release added, and its status at the time

Moved from the README. The current status of every feature is in [STATUS.md](STATUS.md); since then, the V3 features below marked "Implemented, not run" are off by default behind `[experimental]` in config.toml.

## V2 upgrade: career discovery and phone reader

See [docs/V2_SETUP.md](V2_SETUP.md) for architecture, setup and APK build steps.
The Android reader uses Capacitor and bundles its screens; Expo Go is not required.
Local Colibri remains responsible for AI analysis. Finished briefings can sync to a
private cloud reader that needs your login.

### V2 status

Only items tested on the real app are listed as working. Last updated 2026-11-06.

| Feature | Status | How it was checked |
|---|---|---|
| Desktop interface (Today, Sources, Settings) | Working | Opened in a browser with real data at desktop and 390px widths |
| Careers-page discovery | Working for Greenhouse, Lever and Ashby links in the page's HTML | Real sites. Pages that load jobs with JavaScript find nothing and need manual entry |
| Colibri CV matching | Working | Real job analysed by the local model; result cited profile facts |
| Private cloud sync (Supabase) | Working | Real briefings uploaded; `scripts/verify_cloud.py` passed on the live project with two accounts |
| Android app: login, briefings, Summaries, source links | Working | Installed on a real phone |
| Reading with the laptop off | Working | Laptop shut down, phone on mobile data |
| Reading with no internet | Working | Airplane mode, with a saved login session |
| Sign-out clears the phone's copies | Working | Checked in Airplane mode after signing out |
| A new briefing reaching the phone | Working | Run on the laptop, uploaded automatically, confirmed in the cloud and on the phone |
| Automatic updates to the app | Not set up | The app has a test signature. A permanent signature needs a reinstall once |

Limits: new briefings need the laptop and Colibri running. Start with
`powershell -File scripts\start-v2.ps1`, because `scripts\start.cmd` does not load the cloud
settings. Supabase's free plan can pause a project after about a week of low activity.

## V3: wider discovery, funded startups, contacts, twice-daily sweeps

See [docs/V3_SETUP.md](V3_SETUP.md). **Implemented in code, not yet run or tested.** Every row below
is "Awaiting your validation" until the commands in that guide pass on this laptop.

| Feature | Status | Needs |
|---|---|---|
| Wellfound import, YC jobs, cross-source merge | Implemented, not run | Wellfound: your saved listings. YC: nothing |
| Hiring companies (replaces Funded startups): employers with eligible Bengaluru or India-remote openings, grouped from the same records as Jobs; investor evidence optional | Tested on a copy of real data: 17 companies, 287 openings | Nothing; **Refresh hiring** rechecks boards |
| Portfolio discovery: YC India (`/companies/location/india`; robots.txt disallows the filtered directory and the API), WestBridge portfolio | Tested live on a copy: 50 YC + 12 WestBridge companies | Accel, Peak XV, Lightspeed and WestBridge announcements still need page addresses |
| Role families from duties, location groups, pay bands | Implemented, not run | Your profile facts and "not claimed" list |
| Contacts and drafts from public pages | Implemented, not run | Nothing; LinkedIn is not integrated |
| Automatic sending | Not available | An authorised messaging integration (none exists for this project) |
| Run now, shared lock, 08:00/20:00 schedule, Windows task | Implemented, not run | Opt-in: scripts\schedule-install.ps1 |
| Larger-model escalation and replay comparison | Implemented, not run | A larger Colibri model you choose; nothing is downloaded |

## Phone access on your Wi-Fi, and the Edge side panel

See [docs/LAN_AND_PANEL.md](LAN_AND_PANEL.md). **Implemented in code, not yet run or tested.** PC-only mode is unchanged and remains the default. LAN mode serves one signed-in HTTPS address and refuses to start without a password, a trusted certificate and a private address. The `extension/` folder is an Edge side panel for comparing jobs you paste, with no access to LinkedIn or other pages.

## Comparing models (as first documented)

`eval.run_eval model` runs against whichever model the server is serving, refuses if that isn't the model you name, and saves raw outputs plus automatic checks to `<data dir>\evals`. Switching to 9B stops the 4B server, and with it NextWord's tutor, so do it when nothing else needs the model:

```bat
cd <your GitHub folder> && local-ai\start-colibri.cmd 9b
cd signaldesk && .venv\Scripts\python -m eval.run_eval model --model-id qwen3.5-9b-q4km
.venv\Scripts\python -m eval.run_eval compare D:\LocalAI\signaldesk\evals\model-qwen3-4b-...json D:\LocalAI\signaldesk\evals\model-qwen3.5-9b-...json
cd .. && local-ai\start-colibri.cmd 4b
```

The comparison report has an empty **Human review** column. Automatic checks test format and rules, not which model is better.

The human-review steps now live in [HUMAN_REVIEW.md](HUMAN_REVIEW.md).
