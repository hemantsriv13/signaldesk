# V3 validation record (2026-11-15)

Run on a copy of the live data folder (`D:\LocalAI\signaldesk-v4-copy`), never the live folder. The
copy left out `delivery.env` and `rls-test.env`, so nothing synced to the cloud, and used its own port
(8792) so a CLI sweep could not reach an app running on the live data. The four V3 switches under
`[experimental]` were on in the copy's `config.toml`; the schedule and side panel stayed off.
Model: Colibri, qwen3-4b-instruct-2507-q4km, 2,048-token context. Branch `v4-outcomes`.

Counts and outcomes only: no person, profile fact or posting text is recorded here.

## Steps from V3_SETUP.md "Validate"

| Step | Ran | Result |
|---|---|---|
| 1. `scripts\test.cmd` | yes | Passed: pytest, 19 evaluation cases, type check |
| 2. Web build | yes | Passed (desktop and mobile) |
| 3. Restart with `start-v2.ps1` | **no, on purpose** | It loads the live folder's `delivery.env`, which would have uploaded the copy's briefings. Started with `python -m signaldesk --home <copy>` instead |
| 4a. `sweep --scope funding` | yes | Done, 0 failures |
| 4b. Full `sweep` | yes | Done in about 4 minutes, 0 failed sources, 0 failed tasks |
| 5. Windows schedule | no | Needs your go-ahead to install the task |
| 6. Replay with a larger model | no | Needs a model switch (Phase 5) |

## V3 rows

| Feature | Ran | Result | Broken or open |
|---|---|---|---|
| Wellfound import | no | Needs your saved Wellfound listings | Not validated |
| YC jobs | yes | 20 listings read; 17 new, kept unverified; 0 employer boards found on the page | All 37 YC rows are engineering roles. Locations bleed from the next listing ("Remote Apply <other company>"); employer names come from URL slugs ("Hazel 2") |
| Cross-source merge | yes | 0 merges | No YC employer has a board in Sources, so it could not be exercised on real data (fixture tests pass) |
| Role families from duties | yes | 13 unclear titles; 12 model checks plus 15 earlier ones | Precision is poor. Of 23 decided model checks, about 8 look right and about 12 wrong (Claude's reading of the titles and quotes; yours to confirm) (engineering, accounting and security titles placed in strategy & ops or AI product; two finance controllers placed in founder's office). 19 of 61 matches were placed by the model |
| Location groups | yes | Bengaluru 286, remote India 5, uncertain 132, elsewhere 3,471 (open jobs) | **Fixed:** US states ("Remote - California") were "uncertain"; 58 jobs move to elsewhere |
| Pay bands | yes | All 120 matches and To review roles: pay unknown | Only USD pay was disclosed, so INR bands could not be checked on real data (fixture tests pass) |
| Portfolio discovery (YC India, WestBridge) | yes | 50 + 12 companies; 15 careers pages checked, 1 board added, 12 need a manual check, 2 unreachable | Announcement pages have no addresses, so no funding rounds were read |
| Contacts | yes | This sweep: 5 roles checked, 0 found. One role re-run by hand: 3 found from the company's own team page | Of the 5 contacts in the data before the sweep, 2 are customer testimonials from other companies, stored as the employer's people: the team-page lookup redirected to the employer's home page. With the 2 known team-page failures in `tests/test_contacts.py`, discovery is not reliable yet |
| Drafts | yes | Template drafts written for each contact | Every model draft was rejected by the checks (generic praise, company not named, profile fact not cited), so all drafts are the template, which quotes nothing from the posting |
| Run now and the shared lock | yes | A second trigger from the CLI and from the API was refused while a sweep ran; a second process that could not reach the app was refused too | **Fixed:** a second process starting up marked the app's live runs failed and re-queued its tasks |
| Larger-model escalation | no | Needs the 9B or another larger model | Not validated |

## Also fixed

- `config.toml` saved with a byte-order mark (Notepad, PowerShell 5) stopped SignalDesk from starting.
