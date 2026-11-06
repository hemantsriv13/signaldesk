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
- Optional automatic WhatsApp template submissions for new briefings.
- Native Android project using Capacitor. Its APK runs without Expo Go or a dev server.

## Architecture and costs

Your laptop collects sources, trains nothing for matching, and runs Qwen through Colibri.
It only makes outbound HTTPS calls to Supabase and, if enabled, Meta. The laptop API
remains bound to loopback. It is never exposed publicly to make the phone work.

Supabase stores a read-only copy of selected finished briefings with authenticated,
owner-scoped reads enforced by row-level security. The APK uses only a public project
key plus your user login. Its bundle never needs a service-role key or Meta token.
Raw CV files, profile facts, full articles, and the local database are not synced.
Briefing summaries may still reveal your interests and inferred fit; they are private
account data. Only send to your opted-in WhatsApp recipient.

New collection, AI summaries and new WhatsApp submissions require the laptop process
running. Cloud copies remain readable while it is off. An always-on cloud worker and
remote AI inference are not included. No paid LLM API has been added. Cloud hosting,
build infrastructure and WhatsApp can incur provider charges; check their current
plans rather than treating the whole deployment as free.

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
   SIGNALDESK_OWNER_ID. This is not your WhatsApp number.
4. Copy `cloud/delivery.env.example` to your local data directory as `delivery.env`.
   Populate Supabase values, keeping WhatsApp disabled initially. Do not commit it.
5. Start via `powershell -File scripts\start-v2.ps1`. If PowerShell execution is blocked,
   follow your own Windows policy or set the variables in your terminal and run the
   normal launcher. The script parses values as data; it does not execute the file.
6. In Profile and settings, check **Cloud reader & WhatsApp**, then sync.
7. For a hosted web reader, set the public values in `web/.env.mobile.local` using
   `web/.env.mobile.example` as a guide, run `npm run build:mobile` in web, and deploy
   `web/dist-mobile` on your chosen static HTTPS host. No paid hosting is assumed.
   Preserve the `.well-known` directory when deploying.
8. Test that signed-out requests cannot read rows. Sign in as a second test user and
   verify they cannot read the first user's rows, including by explicit digest UUID.
   Do this on the actual deployed project: Python mocked HTTP tests do not prove RLS.

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

## 4. Open a briefing from WhatsApp into the APK

Choose the HTTPS reader domain first. Messages link to:

`https://YOUR_READER_DOMAIN/?digest=BRIEFING_UUID`

The public URL contains only a record ID. Reading its contents still requires login.
The web reader is the fallback when the app is absent or Android has not verified it.
To enable verified Android App Links:

1. Obtain your APK signing certificate's SHA-256 fingerprint (Android Studio or
   `keytool -list -v -keystore YOUR_KEYSTORE`). Debug and release keys differ.
2. From the repo root run:

   `python mobile-tools/configure-links.py --host YOUR_READER_DOMAIN --fingerprint AA:BB:...`

   Supply the full 32-byte fingerprint, not the abbreviated example.
3. Rebuild the APK and redeploy the mobile web build. Serve the generated file at
   `https://YOUR_READER_DOMAIN/.well-known/assetlinks.json`, publicly accessible without
   login, with application/json content type and no redirect.
4. Test a cold app launch and an already-open app using a real message on the phone.
   Correct domain/signature association is required; a JS handler alone cannot guarantee
   Android will open the app. The link selects the correct briefing after login.

No placeholder domain or certificate association is shipped as if it were verified.

## 5. Configure automatic WhatsApp delivery

Use the official WhatsApp Business Platform. Provision a sender, an access token,
recipient opt-in, appropriate billing, and an approved template. Your normal WhatsApp
account alone does not supply these API credentials. Provider approval and pricing
are external setup steps; this code cannot approve its own template.

Create a template matching this exact component structure:

- One body text variable: a compact SignalDesk summary (one parameter). SignalDesk sends it as a single line because Meta rejects line breaks in variables.
- One URL button, index 0, with URL `https://YOUR_READER_DOMAIN/?digest={{1}}`.
  Its dynamic variable is the synced briefing UUID. Keep its domain consistent with
  SIGNALDESK_READER_URL and your Android App Links association.

Set the server-only variables in delivery.env:

- WHATSAPP_ACCESS_TOKEN, WHATSAPP_PHONE_NUMBER_ID (sender ID, not recipient number)
- WHATSAPP_TO (recipient international digits, e.g. country code followed by number)
- WHATSAPP_GRAPH_VERSION (a currently supported Meta Graph API version)
- WHATSAPP_TEMPLATE and WHATSAPP_LANGUAGE (must match the approved template)
- SIGNALDESK_READER_URL (your deployed HTTPS reader URL)
- SIGNALDESK_WHATSAPP_ENABLED=true only when ready to submit real messages

Restart with the V2 launcher. Existing briefings sync without flooding WhatsApp;
only briefings created after enabling automatic delivery are eligible. Enable the
existing desktop daily schedule and keep the laptop awake for fresh daily results.
The worker checks each minute. Cloud sync must succeed before message submission.

States are **submitted**, **rejected**, or **submission_unknown**. Submitted means
Meta accepted the request, not that the phone received or read it. Delivery receipt
webhooks are not implemented in this release. Timeouts or process interruption can
leave uncertainty; those sends are not automatically retried to avoid duplicates.
Rejected messages need manual investigation; after correcting the configuration, explicitly retry through the desktop delivery settings.
never erase uncertain state just to make an indicator green. No WhatsApp Web bot is
included. No real external send is exercised by the automated test suite.

## Verification checklist

- Python tests, deterministic rule evaluation, desktop and mobile production builds.
- Desktop source discovery: valid board, no board, blocked page and wrong employer.
- Real-device 390px-class layout, font scaling, keyboard, contrast and navigation.
- Create account, verify RLS isolation, sync a real briefing and refresh on phone.
- Turn laptop off; verify a synced briefing remains readable over mobile data.
- Cache a briefing; turn phone network off and verify device copies are labelled.
- Confirm sign-out clears the device cache.
- Build/sign/install APK; verify launch without Expo Go or a local dev server.
- Confirm a real approved WhatsApp template reaches your own opted-in phone.
- Verify HTTPS link opens the same briefing in cold/warm APK and web fallback.

Actual account setup, live delivery, RLS deployment, domain verification and physical
phone checks must be reported independently from mocked tests and source generation.
