// Live access to the laptop over Tailscale (or home Wi-Fi), using the signed-in HTTPS address and a
// phone token paired from the laptop. Short timeouts: when the laptop is asleep or off, the app falls
// back to the cloud copy at once. No dependency on React, so it runs under node --test too.
import type { QueuedAnswer, SendResult } from "./answer-queue"

export interface Live { url: string; token: string }
export interface LiveBatch { tasks: unknown[]; answered: Record<string, string> }

export function validLive(l: Live | null): l is Live {
  if (!l || !l.token.startsWith("sdm_")) return false
  try { const u = new URL(l.url); return u.protocol === "https:" && !u.username && !u.password && u.pathname === "/" } catch { return false }
}

const headers = (l: Live) => ({ authorization: `Bearer ${l.token}`, "content-type": "application/json" })
const base = (l: Live) => l.url.replace(/\/+$/, "")

/** Today's batch from the laptop, or null when it cannot be reached (asleep, off, no tunnel). */
export async function liveToday(l: Live, ms = 4000, f: typeof fetch = fetch): Promise<LiveBatch | "unpaired" | null> {
  try {
    const r = await f(`${base(l)}/api/phone/projects`, { headers: headers(l), signal: AbortSignal.timeout(ms) })
    if (r.status === 401) return "unpaired"
    if (!r.ok) return null
    return await r.json() as LiveBatch
  } catch { return null }
}

export async function liveAnswer(l: Live, a: QueuedAnswer, ms = 8000, f: typeof fetch = fetch): Promise<SendResult> {
  try {
    const r = await f(`${base(l)}/api/phone/projects/${encodeURIComponent(a.task_id)}/answer`, {
      method: "POST", headers: headers(l), signal: AbortSignal.timeout(ms),
      body: JSON.stringify({ id: a.id, verdict: a.verdict, note: a.note, answered_at: a.answered_at }),
    })
    if (r.ok) return { ok: true }
    if (r.status === 409) return { ok: false, offline: false, code: "23505" }        // already answered: same rule as the cloud
    if (r.status === 401) return { ok: false, offline: true }                        // unpaired: let the cloud take it
    return { ok: false, offline: false, code: String(r.status), message: `The laptop refused this answer (HTTP ${r.status}).` }
  } catch { return { ok: false, offline: true } }
}
