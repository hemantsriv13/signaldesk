# Project Coach handoff — 2026-11-15
- Branch: project-coach, based on local v4-outcomes; small local commits only.
- No merge, push, sibling clone writes, Supabase changes or APK build.
- Step 1 implemented: config, three read-only adapters, Git metadata, SQLite
  migration, daily selection, human responses, exports, fifth agent and desktop UI.
- Step 1 verification: fixtures/browser pass; private copied-data run PENDING.
- Step 2 NOT started: cloud/schema.sql unchanged; owner must run future SQL.
- Step 3 NOT started: Mobile.tsx unchanged; no phone Projects/offline answers yet.
- Step 4 NOT started: notifications remain unimplemented.
- docs/PROJECT_COACH.md contains contracts, export details and four deferred designs.
- Owner authorized focused read-only source/format inspection after the first stop.

## Verification
- Full Python suite: 314 tests pass; deterministic evaluation: 19 cases pass.
- Project Coach: 19 fixture tests, including blind payloads, persistence, fairness,
  concurrency, immutable answers, export conflicts and permission-denied paths.
- TypeScript and desktop production build pass with commands below.
- Projects.tsx lint passes. Whole-app strict lint finds existing warnings elsewhere.
- Real local browser on invented data: save, skip, refresh, export, reload; widths
  390/1440/1728; 390 touch with throttled network and disabled cache all passed.
- Better Design principles, review rules and comprehension checks completed.
- Rendered spacing: completed; zero critical/serious findings across six states.
- Remaining moderate spacing findings concern the existing shell and alignment.
- Read-only adapters accepted current sibling review formats and all Git metadata.
- No real-data end-to-end test, cloud/RLS, mobile build, APK, notification or model run.
- Private profile/CV/contacts/jobs/database contents were never printed or committed.

## Access and runtime limitations
- D:\LocalAI\signaldesk-v4-copy is sandbox-inaccessible. Live home never accessed.
- Asked owner to copy it to data/project-coach-copy, excluding delivery.env and
  rls-test.env; copy not confirmed/present at last check. Do not use live data.
- .venv launcher points to inaccessible Python312; workspace Python 3.12.10 works.
- Node v24.22.1: ordinary npm hits C:\ realpath denial in this sandbox.
- Native Vite config loading plus symlink flags works; no dependencies added.
- Browser fixtures/artifacts are ignored under data/; no private-data screenshots.

## Exact commands (PowerShell, from SignalDesk root)
The helper uses the existing workspace runtime and SignalDesk dependencies:
```powershell
$py = '..\.pushback-tools\python\python.exe'
function sdp { & $py -B -c "import runpy,sys; sys.path[:0]=['.','.venv/Lib/site-packages']; m=sys.argv.pop(1); sys.argv[0]=m; runpy.run_module(m,run_name='__main__')" @args }
New-Item -ItemType Directory -Force '..\.project-coach-checks' | Out-Null
$env:SSL_CERT_FILE = & $py -c "import sys;sys.path.insert(0,'.venv/Lib/site-packages');import certifi;print(certifi.where())"
Remove-Item Env:SSL_CERT_DIR -ErrorAction SilentlyContinue
sdp pytest -q --basetemp=../.project-coach-checks/next-run
sdp eval.run_eval rules
$env:NODE_OPTIONS = '--preserve-symlinks --preserve-symlinks-main'
Push-Location web
node node_modules/typescript/bin/tsc -b
node node_modules/vite/bin/vite.js build --configLoader native
Pop-Location
# ONLY once the private COPY exists and has [[project]] entries:
sdp signaldesk.projects collect --home data/project-coach-copy
sdp signaldesk.projects export --home data/project-coach-copy
$env:SIGNALDESK_SUPABASE_SERVICE_KEY = '' # prevent existing briefing sync
sdp signaldesk --home data/project-coach-copy --no-start-model --port 8793
```
Open http://127.0.0.1:8793/#/projects. Keep a new basetemp for each test run.

## Decisions waiting on owner
- Provide/confirm the copied home, then verify collection without printing its data.
- Review Step 1 before authorizing Step 2; do not proceed automatically.
- NextWord export is one ZIP retaining consumer sheet names/key.json plus audit JSON;
  Pushback is CSV; SignalDesk is versioned JSON. Nothing imports into sibling clones.
