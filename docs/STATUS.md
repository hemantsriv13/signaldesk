# What is verified, and what is experimental

A feature is **verified** only where an existing record says how it was checked on a real run. Everything
else is **experimental**: the code exists and mocked tests may cover it, but nobody has yet confirmed it
works on this laptop with real sources, the real model or a real device.

Experimental features that could act on their own (fetch new sites, run on a timer, open an API) are
**off by default and cannot run** until you switch them on in `<data dir>\config.toml`:

```toml
[experimental]
listing_sources = false        # Wellfound import and Y Combinator jobs
funding_announcements = false  # investor announcement pages
duty_role_families = false     # role families from duties, and model checks of unclear titles
contacts = false               # contact discovery and outreach drafts
schedule = false               # 08:00/20:00 in-app schedule and the Windows scheduled task
side_panel = false             # Edge side panel API and pairing tokens
```

The larger model and LAN mode already had their own off-by-default settings (`[model] escalation_model_id`,
`[lan] enabled`); they are unchanged. `tests/test_experimental.py` proves each default. In the app, each
of these carries the label **Experimental: not yet validated**.

## Local core

| Feature | Status | Evidence, or the commands that would verify it |
|---|---|---|
| Mocked tests and deterministic rule evaluation | verified | `pytest` and `python -m eval.run_eval rules`, run on every push by `.github/workflows/ci.yml` |
| Job Scout: Greenhouse, Lever and Ashby boards; location class, pay wording, review bucket; new/changed/closed | verified | [EVALUATION.md](EVALUATION.md) §2: live run 2026-11-02, 15 boards, 3,799 listings |
| Reading Scout: RSS/Atom feeds, full text vs excerpt | verified | EVALUATION.md §2: 14 feeds, 112 items |
| Model queue, job fit, reading cards, case studies (4B, one request at a time) | verified | EVALUATION.md §2: 57 model calls, all answered; retries and gating fixed during the run |
| Briefing (Digest Editor) and Regenerate from the UI | verified | EVALUATION.md §2 "Regenerate from the UI" |
| Desktop interface: Today, Sources, Settings | verified | README V2 status: opened with real data at desktop and 390 px |
| Careers-page discovery (Greenhouse, Lever, Ashby links in the page HTML) | verified | [V2_VALIDATION.md](V2_VALIDATION.md): real pages, including refusals |
| CV matching through the local model | verified | V2_VALIDATION.md: real job analysed, cited profile facts |
| Hiring companies (employers with eligible openings) | verified | README V3 table: tested on a copy of real data, 17 companies, 287 openings |
| Portfolio discovery: YC India, WestBridge portfolio | verified | README V3 table: tested live on a copy, 50 YC + 12 WestBridge companies |
| Automatic checks on 4B model output | verified | EVALUATION.md §3: 12 of 12 items valid |
| **Human review of job-fit judgements** | not done | EVALUATION.md "Human review": blank |
| 9B model comparison | not run | EVALUATION.md §3; commands in the README, "Comparing models" |
| Wellfound import and YC jobs (`listing_sources`) | experimental, off | Set the switch, restart, import a saved Wellfound list under Sources → Discovery sources, and run `python -m signaldesk sweep --scope jobs`. Check that listings match employer boards and unmatched ones stay "Not yet on employer's board" |
| Investor announcement pages: WestBridge, Accel, Peak XV, Lightspeed (`funding_announcements`) | experimental, off | Set the switch, add a confirmed page address in Sources, run `python -m signaldesk sweep --scope funding`, and compare the dated rounds with the announcement pages |
| Role families from duties, and model checks of unclear titles (`duty_role_families`) | experimental, off | Set the switch, run a jobs sweep, and check placements against the postings, especially "Special Projects" roles and sales roles that mention strategy. Off means families come from the title, as in the verified first release |
| Location groups and pay bands | experimental, not switched | Code runs on every job (no switch; turning it off would change the Jobs page). Verify by checking Jobs filters against a sample of real postings |
| Run now with a scope, and the lock shared across processes | experimental, not switched | Run now from Today while `python -m signaldesk sweep` runs in a second window; the second should report the sweep already running |
| Contacts and outreach drafts (`contacts`) | experimental, off | Set the switch, mark a job Interested, choose Find contacts, and check that every person's page names them and no profile link was guessed |
| Automatic sending of messages | not available | No authorised messaging integration exists |
| 08:00/20:00 schedule and Windows task (`schedule`) | experimental, off | Set the switch, then `powershell -ExecutionPolicy Bypass -File scripts\schedule-install.ps1` and `Start-ScheduledTask -TaskPath '\SignalDesk\' -TaskName 'SignalDesk sweep 0800'`; remove with `scripts\schedule-remove.ps1` |
| Larger-model escalation and replay comparison | experimental, off | Set `[model] escalation_model_id`, then `python -m eval.run_eval replay --label small`, switch Colibri, `replay --label large --model-id ID`, `replay-report A B` ([V3_SETUP.md](V3_SETUP.md)) |
| LAN mode (phone on your Wi-Fi) | experimental, off | The acceptance checks in [LAN_AND_PANEL.md](LAN_AND_PANEL.md) §6, all unverified |
| Edge side panel (`side_panel`) | experimental, off | Set the switch, then LAN_AND_PANEL.md §4 step 4 and the last three rows of §6 |

## Optional parts

| Feature | Status | Evidence, or the commands that would verify it |
|---|---|---|
| Private cloud sync (Supabase) | verified | V2_VALIDATION.md "Live checks": `scripts/verify_cloud.py` passed with two accounts |
| Android reader: login, briefings, Summaries, source links | verified | V2_VALIDATION.md: owner-reported on a real phone |
| Reading with the laptop off, in Airplane mode, and sign-out clearing the phone | verified | V2_VALIDATION.md: owner-reported on a real phone |
| A new briefing reaching the phone | verified | V2_VALIDATION.md: uploaded automatically and confirmed on the phone |
| Font scaling and keyboard use on the phone | not tested | V2_VALIDATION.md |
| Automatic app updates | not set up | The APK has a test signature; a permanent one needs a reinstall once |
