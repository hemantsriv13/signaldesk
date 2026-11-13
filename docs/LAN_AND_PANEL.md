# SignalDesk on your home network, and the Edge side panel

Status: **implemented in code, nothing executed.** No build, test, server, request, certificate,
firewall or encryption command was run while writing this. Every check below is unverified until
you run it.

## 1. What is exposed today (established from the code)

| Component | Listens on | Authentication | From another device on the Wi-Fi |
|---|---|---|---|
| SignalDesk app and API (`python -m signaldesk`, `scripts\start.cmd`) | `127.0.0.1:8780` (`[server] host`; non-loopback hosts are refused at startup) | None. Requests must name this PC in the Host header and writes must come from its own pages | Not reachable by design (runtime unverified) |
| Colibri model server | Started by your sibling `local-ai\start-colibri.cmd` with `--host 127.0.0.1 --port 8000` (seen in the process list earlier in this project; not part of this repo) | None | Not reachable if that launcher keeps 127.0.0.1 (runtime unverified) |
| Vite dev server (`npm run dev`) | localhost only unless started with `--host` | None | Only if you start it with `--host`; don't |
| Supabase cloud copies | Outbound only, to your project | Secret key on this PC; phone reads with login + row-level security | n/a: nothing on the PC is opened |
| Android reader APK | Reads Supabase only | Your login | Never talks to the PC |

There are no other ports, older routes or live-update streams (the app polls). There is no export
endpoint; briefings are also written as Markdown to `<data dir>\digests`. Anyone using **this PC**
can read and trigger everything on 127.0.0.1:8780 today. That stays the same in PC-only mode
unless you set `[auth] require_login_local = true`.

## 2. What changed in code

- **Two modes.** PC-only (default) is unchanged: plain HTTP on 127.0.0.1. LAN mode (`--lan` or
  `[lan] enabled = true`) adds **one** HTTPS listener on your PC's private Wi-Fi address. The app on
  127.0.0.1 and Colibri stay on loopback. If anything is missing (password, private bind address,
  certificate, key, certificate names, expiry) SignalDesk prints what to fix and **does not start**;
  there is no plaintext LAN listener in any case.
- **Sign-in on the HTTPS entry point** for every `/api/*` route (jobs, contacts, outreach, briefings,
  settings, runs, panel). Owner password stored as a salted scrypt hash in `<data dir>\auth.json`.
  Server-side sessions in a `__Host-` cookie (Secure, HttpOnly, SameSite=Strict); idle 12 h, absolute
  7 days; logout and "Sign out other devices". Writes need the session's CSRF token and an allowed
  Origin. Host header must be one of `[lan] hostnames`. Failed sign-ins: 5 per address and 30 overall
  per 15 minutes. HSTS, CSP, no-store, nosniff and frame denial on responses.
- **Side-panel tokens.** Separate, revocable, 90-day credentials that reach only `/api/panel/*` (parse,
  import, compare, decide, metrics). They cannot reach settings, profile, contacts, outreach, exports,
  runs, sources or token management. Only their hash is stored; the token is shown once. Revoke in
  Settings → Security or `python -m signaldesk auth revoke-panel`.
- **Imported URLs.** Opening a link in your browser is separate from SignalDesk fetching it.
  SignalDesk fetches an imported URL only when it is a Greenhouse, Lever or Ashby page or a careers
  site you already track. LinkedIn, Wellfound and other aggregators are never fetched. Every fetch
  rejects loopback, private, link-local, CGNAT, multicast, reserved and unspecified addresses in IPv4
  and IPv6 (including IPv4-mapped, 6to4, Teredo and NAT64 forms) before any request and at every
  redirect. The connection is made to the validated address (no second DNS lookup), environment proxies
  are ignored, and size, timeout and retry limits apply. Job text is shown as text (React escaping;
  the panel uses `textContent`) and sent to Colibri only as quoted data; no agent can run tools or send
  messages from it.
- **Cloud copies.** Jobs you pasted yourself (manual, Wellfound, side panel) are now left out of the
  Supabase copies unless you add `SIGNALDESK_SYNC_MANUAL_IMPORTS=true` to `delivery.env`. Contacts,
  drafts, profile facts and panel labels were never synced and still are not.
- **Logs** redact panel tokens, Supabase keys, JWTs, bearer headers and the session cookie.

## 3. Where your data is (and how to check encryption)

| What | Where |
|---|---|
| Database, WAL and shared-memory files | `D:\LocalAI\signaldesk\signaldesk.db`, `-wal`, `-shm` |
| SQLite temporary files | `%TEMP%` (on C:) |
| Profile (CV facts), sign-in hash, cloud keys, privacy-check logins | `D:\LocalAI\signaldesk\profile.json`, `auth.json`, `delivery.env`, `rls-test.env` |
| LAN certificate and private key | `D:\LocalAI\signaldesk\tls\` (after setup) |
| mkcert root CA private key | `mkcert -CAROOT` (usually `%LOCALAPPDATA%\mkcert`, on C:) |
| Logs, Markdown briefings, evaluation outputs | `D:\LocalAI\signaldesk\logs`, `digests`, `evals` |
| Backup from the V2 upgrade | `D:\LocalAI\signaldesk\backup-before-v2` |
| Side-panel token | Your Edge profile (`%LOCALAPPDATA%\Microsoft\Edge\User Data`), extension local storage |
| Android signing key, phone installer | `%USERPROFILE%\.android\debug.keystore`, `Downloads\SignalDesk-reader.apk` |

Read-only checks (nothing is changed):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\check-storage.ps1
# More detail, in an elevated PowerShell:
manage-bde -status C:
manage-bde -status D:
```

This PC runs Windows 11 Home Single Language. Full BitLocker management is not available on Home;
"Device encryption" (Settings → Privacy & security → Device encryption) may be, and may not cover D:.
If D: shows OFF, your database, profile and keys are unencrypted at rest. Nothing here enables
encryption or moves data. If you turn encryption on yourself, save the recovery key somewhere other
than this PC (your Microsoft account or on paper). For backups, encrypt the copy itself (for example a
7-Zip AES-256 archive whose password lives in your password manager) and keep it off D:. The old
`backup-before-v2` folder is an unencrypted copy of your database and profile; delete it when you no
longer need it.

## 4. Setup, in this order

From `C:\Users\Hemant\Documents\GitHub\signaldesk` in PowerShell.

**Step 1. Checks and build (this PC only).**
```powershell
.venv\Scripts\python -m pytest tests\test_security.py tests\test_v3.py -q
.venv\Scripts\python -m pytest -q
cd web; npm run build; cd ..
Get-NetTCPConnection -State Listen | Where-Object LocalPort -in 8780,8000,8443 | Select-Object LocalAddress,LocalPort,OwningProcess
```
Expected: tests pass; listeners on 8780 and 8000 show `127.0.0.1` only.

**Step 2. Set the sign-in password.**
```powershell
.venv\Scripts\python -m signaldesk auth set-password
```

**Step 3. Start in PC-only mode (unchanged).**
```powershell
powershell -File scripts\start-v2.ps1
```

**Step 4. Load and pair the Edge side panel.**
1. Edge → `edge://extensions` → turn on **Developer mode** → **Load unpacked** → choose the repo's
   `extension` folder. Its permissions read "storage" and "side panel" only.
2. Pin it, then click its toolbar button to open the side panel.
3. In SignalDesk: Profile and settings → Security → **Create pairing token**. Copy the token.
4. In the panel: address `http://127.0.0.1:8780`, paste the token, **Connect**, and allow access to
   that one address when Edge asks. (For LAN mode use `https://<PC address>:8443` instead.)

**Step 5. LAN mode (only if you want phone access).**
1. Find the PC's Wi-Fi address: `Get-NetIPAddress -AddressFamily IPv4 -InterfaceAlias Wi-Fi`.
   In your router, give the PC and your phone fixed addresses (DHCP reservation). **Do not** add port
   forwarding.
2. Install mkcert: `winget install FiloSottile.mkcert`, then open a new PowerShell window.
3. Create the certificate:
   `powershell -ExecutionPolicy Bypass -File scripts\lan-setup.ps1 -Address 192.168.1.10`
4. Paste the printed `[lan]` block into `D:\LocalAI\signaldesk\config.toml`.
5. Start: `powershell -File scripts\start-v2.ps1 --lan` (or `scripts\start.cmd --lan`). If it
   prints "LAN mode was not started", fix the listed items.
6. Firewall, in an elevated PowerShell, for your phone's address only:
   `powershell -ExecutionPolicy Bypass -File scripts\lan-firewall.ps1 -Address 192.168.1.10 -Devices 192.168.1.23`
7. Optional: after setup, move `rootCA-key.pem` from `mkcert -CAROOT` to an encrypted USB drive.
   Bring it back only when you renew.

**Step 6. Phone (Android).**
1. Copy `D:\LocalAI\signaldesk\tls\SignalDesk-local-CA.crt` to the phone. This is the **public** CA
   certificate. The private keys never leave the PC.
2. Settings → Security & privacy → More security settings → Encryption & credentials → Install a
   certificate → **CA certificate** → choose the file.
3. In Chrome open `https://192.168.1.10:8443` (exactly a name on the certificate) and sign in.

Renew: rerun `lan-setup.ps1` with the same addresses before expiry (SignalDesk warns 30 days ahead;
the phone keeps trusting the same CA). Revoke trust: on the phone, remove it under Encryption &
credentials → User credentials. On the PC, run `mkcert -uninstall`.

## 5. Rollback

```powershell
powershell -ExecutionPolicy Bypass -File scripts\lan-firewall-remove.ps1    # elevated
powershell -ExecutionPolicy Bypass -File scripts\lan-undo.ps1
```
Then set `[lan] enabled = false` (or delete the `[lan]` block), start without `--lan`, and remove the
CA from your phone. To remove the panel: `edge://extensions` → Remove, and revoke its token in
Settings → Security. To return to the previous code, revert the working-tree changes with Git.

## 6. Acceptance checks (all unverified until you run them)

| Check | How | Expected |
|---|---|---|
| Phone opens trusted HTTPS and signs in | Phone Chrome → `https://<PC>:8443` | No certificate warning; sign-in page; Today after sign-in |
| Signed-out device cannot read jobs, export contacts or trigger a run | From a laptop on the Wi-Fi: `curl.exe -s -o NUL -w "%{http_code}" https://<PC>:8443/api/jobs`, `.../api/outreach`, and `curl.exe -s -X POST -H "Origin: https://<PC>:8443" https://<PC>:8443/api/sweep` (use `--cacert` with the CA file, or `-k` only for this test) | 401, 401, 401 (403 without the Origin header) |
| Old HTTP address and backend/Colibri ports unreachable from the LAN | From another device: `Test-NetConnection <PC> -Port 8780` and `-Port 8000`; `http://<PC>:8443` in a browser | `TcpTestSucceeded : False` for both; plain HTTP to 8443 fails |
| Imported private-network URL rejected before any request | Jobs → Add a job by hand → URL `http://192.168.1.1/job` with no text | Error before any request (not "could not connect") |
| Compare two pasted LinkedIn listings with no LinkedIn access | Copy two job cards on LinkedIn, Ctrl+V into the panel, Read listings, Save and compare | Two results ranked; `edge://extensions` shows no site access for linkedin.com |
| Same job pasted again keeps the decision and doesn't inflate metrics | Shortlist one, paste the same cards again under the same label, open Searches | Still "You: shortlisted"; Reviewed count unchanged |
| Revoking panel access stops imports; the app still works | Settings → Security → Revoke; try Read listings in the panel | Panel shows "Access was revoked…" with Reconnect; the main app keeps working |

## 7. Code changes vs. machine settings

**In code (this repo):** `signaldesk/auth.py`, `lan.py`, `panel.py` (new); `netsafe.py`, `server.py`,
`__main__.py`, `config.py`, `db.py`, `collect.py`, `delivery.py`, `digest.py`; the web app sign-in
and Security settings; `extension/`; `scripts/lan-setup.ps1`, `lan-firewall.ps1`,
`lan-firewall-remove.ps1`, `lan-undo.ps1`, `check-storage.ps1`, and `start-v2.ps1` (passes `--lan`
through); tests.

**Machine settings you apply yourself:** the password (`auth set-password`); mkcert install and its
CA in your Windows trust store; the `[lan]` block in config.toml; the firewall rule; DHCP reservations
on your router; the CA certificate on your phone; loading the extension; any disk encryption or backup
changes.
