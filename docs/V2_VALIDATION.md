# V2 validation record

Prepared 2026-11-06 against the published feature/cv-matching branch, commit fb6e514.

- Python tests: 130 passed (mocked HTTP/model services; no real WhatsApp sends).
- Deterministic rule evaluation: 19 cases, 0 failures.
- Desktop TypeScript/Vite production build: passed.
- Phone-reader TypeScript/Vite production build: passed.
- Capacitor Android project generation and plugin sync: passed.
- Standalone testing APK: generated; Android APK Signature Scheme v2 verification passed.
  Package com.hemant.signaldesk; minimum Android API 24; target API 36.
  SHA-256: 80ca0a94e453da8b1233307c9cec7aa75855989988f173b7767e50b371b00b05.
  This is a debug-signed test build, not a production release or physical-device test.
- Account secrets: none provisioned or embedded.
- Supabase schema/RLS: source prepared; deployment and two-user isolation test pending.
- WhatsApp: template request construction, historical-send suppression, failed-sync
  suppression, timeout handling, explicit rejected-message retry, and deduplication
  tested with mocked HTTP. Provider approval, pricing and actual receipt remain pending.
- App Links: configuration generator included; live domain/certificate verification pending.
- Browser visual inspection could not connect to the isolated local preview. Actual
  desktop/mobile visual checks and a physical-device walkthrough remain required.
- Device caches require a restorable local session. First login or expired credentials
  can require internet access; there is no promise of unlimited offline authentication.

See V2_SETUP.md for the external deployment and device checks. Build/source success
must not be reported as proof of live WhatsApp delivery or real-model accuracy.

## Checks on the real laptop, 2026-11-06

- Python tests: 131 passed, including a new one for the WhatsApp fix below. Rule evaluation: 0 failures.
- Desktop and phone-reader production builds and Capacitor sync: passed.
- Fixed before any live use: the WhatsApp summary contained line breaks, which Meta rejects in
  template variables, so every real send would have failed. Mocked tests could not catch this.
- Discovery on real pages: Notion's Ashby board found; LinkedIn, local addresses and requests from
  other origins refused. Anthropic's and Stripe's pages returned no board (not readable from HTML).
- Colibri CV match on a real job: completed with cited profile facts and the configured local model.
- Phone reader: checked at 390px against a throwaway local stand-in for Supabase. This does not
  prove row-level security, real login, cloud sync or Android behaviour.
- Still not tested: live Supabase, hosted reader, App Links, WhatsApp receipt, APK on a phone.

## Scope change, 2026-11-06

WhatsApp delivery, the hosted reader and App Links were removed at the owner's request.
Earlier lines that mention them describe the kit as received. Briefing summaries now appear
in a Summaries tab in the phone reader.

## Live checks, 2026-11-06

- `scripts/verify_cloud.py` passed on the live Supabase project: signed-out and second-account
  reads returned nothing, and edit, delete and insert attempts from the app logins were refused.
- Owner-reported on a real Android phone: login, Summaries, opening a briefing, source links and
  Back, reading with the laptop shut down on mobile data, Airplane mode reading, and sign-out clearing.
- The APK's contents were scanned: the project URL and public key are present, the secret key is not.
- Not tested: a newly generated briefing reaching the phone, font scaling and keyboard use on the phone.
