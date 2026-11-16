// Offline answer queue for the phone. Plain TypeScript with no React or browser globals, so it runs
// under `node --test` as well as in the app. Everything is namespaced by the signed-in user's id.
//
// An answer is saved here first, then sent. The response id is made on the phone, so a send that
// reached the cloud but lost its reply is recognised on retry instead of creating a second answer.

export interface QueuedAnswer {
  id: string; task_id: string; verdict: string; note: string; answered_at: string
  project: string; title: string; state: "waiting" | "failed"; error?: string
}
export interface KeyValue { get(key: string): string | null; set(key: string, value: string | null): void }
export type SendResult = { ok: true } | { ok: false; offline: boolean; code?: string; message?: string }
export type Send = (a: QueuedAnswer) => Promise<SendResult>
/** The id of your existing cloud answer for a task, null if none, or "offline". */
export type Lookup = (taskId: string) => Promise<string | null | "offline">

export const keys = (uid: string) => ({
  queue: `signaldesk-answer-queue:${uid}`,
  tasks: `signaldesk-projects:${uid}`,
  skips: `signaldesk-project-skips:${uid}`,
  notices: `signaldesk-answer-notices:${uid}`,
})

function readJson<T>(s: KeyValue, key: string, fallback: T): T {
  try { return JSON.parse(s.get(key) ?? "null") ?? fallback } catch { return fallback }
}

export const readQueue = (s: KeyValue, uid: string) => readJson<QueuedAnswer[]>(s, keys(uid).queue, [])
export const readNotices = (s: KeyValue, uid: string) => readJson<string[]>(s, keys(uid).notices, [])
const writeQueue = (s: KeyValue, uid: string, q: QueuedAnswer[]) => s.set(keys(uid).queue, q.length ? JSON.stringify(q) : null)

export function enqueue(s: KeyValue, uid: string, a: Omit<QueuedAnswer, "state">): QueuedAnswer[] {
  const q = readQueue(s, uid)
  if (q.some((x) => x.task_id === a.task_id)) return q           // one answer per task, as on the laptop
  const next = [...q, { ...a, state: "waiting" as const }]
  writeQueue(s, uid, next)
  return next
}

export function discard(s: KeyValue, uid: string, id: string): QueuedAnswer[] {
  const next = readQueue(s, uid).filter((x) => x.id !== id)
  writeQueue(s, uid, next)
  return next
}

let flushing = false

/** Send waiting answers in order. Stops at the first sign of being offline and keeps the rest. */
export async function flush(s: KeyValue, uid: string, send: Send, lookup: Lookup): Promise<{ sent: number; sentTasks: string[]; waiting: number; notices: string[] }> {
  const notices: string[] = [], sentTasks: string[] = []
  if (flushing) return { sent: 0, sentTasks, waiting: readQueue(s, uid).length, notices }
  flushing = true
  let sent = 0
  try {
    for (const a of readQueue(s, uid)) {
      if (a.state !== "waiting") continue
      const r = await send(a)
      if (r.ok) { discard(s, uid, a.id); sent++; sentTasks.push(a.task_id); continue }
      if (r.offline) break
      if (r.code === "23505") {                                    // unique violation: same id, or task already answered
        const existing = await lookup(a.task_id)
        if (existing === "offline") break
        discard(s, uid, a.id)
        if (existing === a.id) { sent++; sentTasks.push(a.task_id); continue }   // the earlier send had arrived
        notices.push(`${a.project}: this item already had an answer, so your phone answer (${a.verdict}) was not sent.`)
        continue
      }
      const q = readQueue(s, uid).map((x) => x.id === a.id ? { ...x, state: "failed" as const, error: r.message || "The cloud refused this answer." } : x)
      writeQueue(s, uid, q)
    }
  } finally { flushing = false }
  if (notices.length) s.set(keys(uid).notices, JSON.stringify([...readNotices(s, uid), ...notices].slice(-10)))
  return { sent, sentTasks, waiting: readQueue(s, uid).length, notices }
}

/** Sign-out: remove everything this account left on the phone, including unsent answers. */
export function clearAccount(s: KeyValue, uid: string) {
  for (const key of Object.values(keys(uid))) s.set(key, null)
}

export function skippedToday(s: KeyValue, uid: string, day: string): string[] {
  const all = readJson<Record<string, string[]>>(s, keys(uid).skips, {})
  return all[day] ?? []
}

export function skip(s: KeyValue, uid: string, day: string, taskId: string) {
  s.set(keys(uid).skips, JSON.stringify({ [day]: [...skippedToday(s, uid, day), taskId] }))   // older days dropped
}
