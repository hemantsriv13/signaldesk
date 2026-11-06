# SignalDesk V2: desktop, private cloud reader and Android APK

## What this release does

- Warmer desktop styling and a clearer Today welcome panel.
- Detects supported Greenhouse, Lever and Ashby boards from employer careers links.
  You review ownership and explicitly enable each board. Detection is not verification.
- Opens LinkedIn searches for Bengaluru and remote India. It does not scrape LinkedIn.
  Search results still need eligibility checks. Unsupported career systems need manual
  import; this release does not claim a universal crawler or a Workday connector.
- Existing CV matching still runs through the local Colibri queue.
- Syncs up to 50 recent saved briefing selections to a private Supabase read model.
- A phone reader shows those cloud copies while the laptop is off, caches copies after
  login, and supports device-local bookmarks. It reads finished briefings rather than
  the whole desktop database; job status edits and agent controls remain on desktop.
- A Summaries tab in the phone reader lists a short overview of each synced briefing.
- Native Android project using Capacitor. Its APK runs without Expo Go or a dev server.

## Architecture and costs

Your laptop collects sources, trains nothing for matching, and runs Qwen through Colibri.
It only makes outbound HTTPS calls to Supabase. The laptop API
remains bound to loopback. It is never exposed publicly to make the phone work.

Supabase stores a read-only copy of selected finished briefings with authenticated,
owner-scoped reads enforced by row-level security. The APK uses only a public project
key plus your user login. Its bundle never needs a service-role key.
Raw CV files, profile facts, full articles, and the local database are not synced.
Briefing summaries may still reveal your interests and inferred fit; they are private
account data.

New collection and AI summaries require the laptop process running. Cloud copies remain readable while it is off. An always-on cloud worker and
remote AI inference are not included. No paid LLM API has been added. Supabase's free
plan pauses a project after about a week of low activity; opening its dashboard or
using the app counts as activity. Check its current limits before relying on it.

## 1. Desktop installation

Bring this release into the existing repo without discarding local changes. Run
`scripts\setup.cmd` to refresh Python dependencies and build the desktop UI.
Start normally with `scripts\start.cmd` for desktop-only use.

## 2. Provision the private cloud reader

1. Create a Supabase project you control.
2. Run `cloud/schema.sql` in its SQL editor. It creates the read model, enables RLS,
   permits authenticated users to read only rows with their own owner_id, and grants
   no browser/mobile write permission. The laptop writes using its server-only key.
3. Create your reader user in Supabase Authentication with email and password. Disable
   public signups if this is solely your private app. Use the user's UUID for
   SIGNALDESK_OWNER_ID.
4. Copy `cloud/delivery.env.example` to your local data directory as `delivery.env`.
   Fill in the Supabase values. Do not commit it.
5. Start via `powershell -File scripts\start-v2.ps1`. If PowerShell execution is blocked,
   follow your own Windows policy or set the variables in your terminal and run the
   normal launcher. The script parses values as data; it does not execute the file.
6. In Profile and settings, check **Phone reader**, then upload.
7. To build the public values into the APK, set them in `web/.env.mobile.local` using
   `web/.env.mobile.example` as a guide. No web hosting is needed.
8. Create a second test user, list both logins in `<data dir>\rls-test.env` (see
   `scripts/verify_cloud.py`) and run `.venv\Scripts\python scripts\verify_cloud.py`. It checks
   the live project: mocked tests do not prove row-level security.

A portable APK can also accept the public project URL/key on its connection screen.
Create the project and account before expecting live content. HTTPS is required.
Device caches are namespaced by account, and cleared on sign-out. Clear app storage
if you want to remove all local authentication/configuration data from the phone.
Android application backup is disabled in the native manifest.

## 3. Build and install an actual APK

Install JDK 21 and the Android SDK required by `web/android/variables.gradle` (API 36
in the generated project, with build-tools 35.0.0 and 36.0.0). Use Android Studio or a configured command-line SDK.
Run `scripts\build-apk.cmd`. The output is:

`web/android/app/build/outputs/apk/debug/app-debug.apk`

This debug-signed standalone APK is suitable for your own device testing. It bundles
its web assets and requires neither Expo Go nor Metro. Cloud reading still needs an
internet connection unless copies were previously cached and a local login session can be restored. A first login or expired session may require internet access.

A manual GitHub Actions workflow is also provided: Actions → Build standalone Android
testing APK → Run workflow. Download the artifact only after the workflow succeeds.
This uses GitHub build minutes and artifact storage under your account's limits;
it does not run automatically on every push. CI debug signing keys may change
between runs, so use a stable private signing key for ongoing installable updates.

For a stable release APK, open `web/android` in Android Studio and use Generate Signed
Bundle / APK → APK. Keep the release keystore and passwords outside Git and reuse the
same signing identity for future updates. An APK signed with a different key cannot
update an installed APK under the same application ID.

If this environment cannot download the SDK or Android dependencies, the repository
still contains the native project and the build script. Do not report an APK as built
until the command produces the file successfully. Physical-device tests are separate.

## Verification checklist

- Python tests, deterministic rule evaluation, desktop and mobile production builds.
- Desktop source discovery: valid board, no board, blocked page and wrong employer.
- Real-device 390px-class layout, font scaling, keyboard, contrast and navigation.
- Create account, verify RLS isolation, sync a real briefing and refresh on phone.
- Turn laptop off; verify a synced briefing remains readable over mobile data.
- Cache a briefing; turn phone network off and verify device copies are labelled.
- Confirm sign-out clears the device cache.
- Build/sign/install APK; verify launch without Expo Go or a local dev server.
- Confirm the Summaries tab lists synced briefings and opens the one you tap.

Actual account setup, RLS deployment and physical phone checks must be reported independently from mocked tests and source generation.
