import { useCallback, useEffect, useState } from "react"
import type { Session, SupabaseClient } from "@supabase/supabase-js"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { discard, enqueue, flush, keys, readNotices, readQueue, skip, skippedToday, type KeyValue, type QueuedAnswer } from "./answer-queue"
import * as reminders from "./reminders"

interface Card {
  project: string; type: string; title: string; text: string; pass_criteria: string; what_this_is: string
  why_it_matters: string; why_sources?: { kind: string; text: string; source?: string; file?: string; line?: number }[]
  unlocks_next: string; evidence: string; verdicts: string[]
}
interface CloudTask { id: string; day: string; project: string; kind: string; status: "open" | "answered" | "skipped"; payload: Card; synced_at: string }
interface Cached { tasks: CloudTask[]; answered: string[]; at: string }

const TASKS = "signaldesk_project_tasks"
const RESPONSES = "signaldesk_project_responses"
const storage: KeyValue = {
  get: (k) => { try { return localStorage.getItem(k) } catch { return null } },
  set: (k, v) => { try { if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v) } catch { /* no device storage */ } },
}
const dayLabel = (d: string) => new Date(d + "T12:00:00").toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" })
const newId = () => crypto.randomUUID()

export function PhoneProjects({ client, session }: { client: SupabaseClient; session: Session }) {
  const uid = session.user.id
  const [data, setData] = useState<Cached | null>(() => { try { return JSON.parse(storage.get(keys(uid).tasks) ?? "null") } catch { return null } })
  const [fromDevice, setFromDevice] = useState(true)
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)
  const [queue, setQueue] = useState<QueuedAnswer[]>(() => readQueue(storage, uid))
  const [notices, setNotices] = useState<string[]>(() => readNotices(storage, uid))
  const [active, setActive] = useState<string | null>(null)
  const [skipTick, setSkipTick] = useState(0)

  const send = useCallback(async (a: QueuedAnswer) => {
    if (typeof navigator !== "undefined" && !navigator.onLine) return { ok: false as const, offline: true }
    const r = await client.from(RESPONSES).insert({ id: a.id, task_id: a.task_id, verdict: a.verdict, note: a.note, answered_at: a.answered_at }).abortSignal(AbortSignal.timeout(10000))
    if (!r.error) return { ok: true as const }
    const offline = r.status === 0 || /abort|timeout|fetch/i.test(r.error.message ?? "") || (typeof navigator !== "undefined" && !navigator.onLine)
    return { ok: false as const, offline, code: r.error.code, message: offline ? undefined : `The cloud refused this answer (${r.error.code || r.status}).` }
  }, [client])
  const lookup = useCallback(async (taskId: string) => {
    const r = await client.from(RESPONSES).select("id").eq("task_id", taskId).limit(1).abortSignal(AbortSignal.timeout(8000))
    if (r.error) return r.status === 0 || /abort|timeout|fetch/i.test(r.error.message ?? "") ? "offline" as const : null
    return (r.data?.[0] as { id: string } | undefined)?.id ?? null
  }, [client])

  const sendWaiting = useCallback(async () => {
    const r = await flush(storage, uid, send, lookup)
    if (r.sentTasks.length) {
      // Sent answers count as answered at once; the next cloud load confirms it.
      setData((d) => {
        if (!d) return d
        const next = { ...d, answered: [...new Set([...d.answered, ...r.sentTasks])] }
        storage.set(keys(uid).tasks, JSON.stringify(next))
        return next
      })
    }
    setQueue(readQueue(storage, uid)); setNotices(readNotices(storage, uid))
    return r
  }, [uid, send, lookup])

  const load = useCallback(async () => {
    setBusy(true); setError("")
    try {
      if (typeof navigator !== "undefined" && !navigator.onLine) throw new Error("offline")   // airplane mode: no waiting
      await sendWaiting()
      const t = await client.from(TASKS).select("id,day,project,kind,status,payload,synced_at").eq("owner_id", uid).order("day", { ascending: false }).limit(12).abortSignal(AbortSignal.timeout(8000))
      if (t.error) throw t.error
      const rows = (t.data ?? []) as CloudTask[]
      const latest = rows[0]?.day
      const tasks = rows.filter((x) => x.day === latest)
      const ids = tasks.map((x) => x.id)
      const r = ids.length ? await client.from(RESPONSES).select("task_id").in("task_id", ids).abortSignal(AbortSignal.timeout(8000)) : { data: [], error: null }
      if (r.error) throw r.error
      const next = { tasks, answered: (r.data ?? []).map((x: { task_id: string }) => x.task_id), at: new Date().toISOString() }
      setData(next); setFromDevice(false); storage.set(keys(uid).tasks, JSON.stringify(next))
    } catch {
      setFromDevice(true)
      setError("No connection. Showing what was saved on this phone; answers wait here and send later.")
    } finally { setBusy(false) }
  }, [client, uid, sendWaiting])

  useEffect(() => {
    void load()
    const again = () => { void load() }
    window.addEventListener("online", again)
    return () => window.removeEventListener("online", again)
  }, [load])

  const day = data?.tasks[0]?.day ?? ""
  const skipped = day ? skippedToday(storage, uid, day) : []
  void skipTick
  const queued = new Set(queue.map((q) => q.task_id))
  const answered = new Set(data?.answered ?? [])
  const reviews = (data?.tasks ?? []).filter((t) => t.kind !== "laptop_reminder")
  const open = reviews.filter((t) => t.status === "open" && !answered.has(t.id) && !queued.has(t.id) && !skipped.includes(t.id))
  const task = open.find((t) => t.id === active) ?? open[0]
  const laptop = (data?.tasks ?? []).filter((t) => t.kind === "laptop_reminder")
  const done = reviews.filter((t) => t.status === "answered" || answered.has(t.id))

  async function save(t: CloudTask, verdict: string, note: string) {
    setQueue(enqueue(storage, uid, { id: newId(), task_id: t.id, verdict, note: note.trim(), answered_at: new Date().toISOString(), project: t.project, title: t.payload.title }))
    setActive(null)
    await sendWaiting()
  }

  return <section aria-labelledby="phone-projects" className="grid gap-4">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <h2 id="phone-projects" className="font-heading text-2xl">Projects</h2>
      <Button variant="outline" disabled={busy} onClick={() => void load()}>{busy ? "Checking…" : "Refresh"}</Button>
    </div>
    <p className="text-xs text-muted-foreground">{day ? `${dayLabel(day)} · ${open.length} left` : "No batch yet"}{data ? ` · ${fromDevice ? "saved on this phone" : "from the cloud"}` : ""}</p>
    {error && <p role="status" className="text-sm">{error}</p>}
    {queue.length > 0 && <div className="mobile-paper grid gap-2" role="status">
      <p className="text-sm font-medium">{queue.length === 1 ? "1 answer" : `${queue.length} answers`} waiting to send</p>
      <p className="text-xs text-muted-foreground">Sends when you are back online.</p>
      {queue.filter((q) => q.state === "failed").map((q) => <p key={q.id} className="text-sm text-(--destructive-text)">{q.project}: {q.error} <button className="underline" onClick={() => setQueue(discard(storage, uid, q.id))}>Remove</button></p>)}
    </div>}
    {notices.map((n) => <p key={n} className="text-sm text-(--warning-text)">{n}</p>)}

    {task ? <>
      {open.length > 1 && <nav aria-label="Today's reviews" className="flex flex-wrap gap-2">{open.map((t, i) =>
        <Button key={t.id} variant={t.id === task.id ? "secondary" : "outline"} aria-current={t.id === task.id ? "step" : undefined} onClick={() => setActive(t.id)}>{i + 1}. {t.project}</Button>)}</nav>}
      <PhoneCard key={task.id} task={task} onSave={(v, n) => save(task, v, n)} onSkip={() => { skip(storage, uid, day, task.id); setActive(null); setSkipTick((n) => n + 1) }} />
    </> : <div className="mobile-paper"><h3 className="font-heading text-xl">{reviews.length ? "Done for today" : "Nothing to review"}</h3>
      <p className="mt-2 text-sm">{reviews.length ? "New reviews come with tomorrow's batch." : "Your laptop prepares the batch."}</p></div>}

    {done.length + queue.length > 0 && <div className="grid gap-1">
      <h3 className="text-sm font-semibold">Answered</h3>
      {done.map((t) => <p key={t.id} className="text-sm">{t.project} · answered</p>)}
      {queue.map((q) => <p key={q.id} className="text-sm">{q.project} · {q.verdict} · {q.state === "failed" ? "not sent" : "waiting"}</p>)}
    </div>}
    {laptop.length > 0 && <div className="grid gap-2">
      <h3 className="text-sm font-semibold">On your laptop</h3>
      {laptop.map((t) => <p key={t.id} className="text-sm text-muted-foreground">{t.project}: {t.payload.text}</p>)}
    </div>}
    <ReminderSettings />
  </section>
}

function PhoneCard({ task, onSave, onSkip }: { task: CloudTask; onSave: (verdict: string, note: string) => Promise<void>; onSkip: () => void }) {
  const c = task.payload
  const [verdict, setVerdict] = useState("")
  const [note, setNote] = useState("")
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)
  return <article className="mobile-paper grid gap-5">
    <div><p className="text-xs uppercase tracking-widest text-primary">{c.project}</p><h3 className="mt-2 font-heading text-2xl leading-tight">{c.title}</h3></div>
    <div className="grid gap-1"><h4 className="text-sm font-semibold">What this is</h4><p className="text-sm">{c.what_this_is}</p></div>
    <div className="grid gap-1"><h4 className="text-sm font-semibold">Why it matters</h4><p className="text-sm">{c.why_it_matters}</p>
      {!!c.why_sources?.length && <p className="text-xs text-muted-foreground">Sources: {c.why_sources.map((f) => f.kind === "readme" ? `${c.project} ${f.file} line ${f.line}` : f.source).join(" · ")}</p>}</div>
    <div className="grid gap-1"><h4 className="text-sm font-semibold">What it unlocks</h4><p className="text-sm">{c.unlocks_next}</p></div>
    <div className="grid gap-1"><h4 className="text-sm font-semibold">Text to judge</h4><p className="whitespace-pre-wrap break-words text-sm leading-relaxed">{c.text}</p></div>
    <details><summary className="min-h-11 cursor-pointer py-3 text-sm font-medium">Source and facts</summary><pre className="max-h-[28rem] overflow-y-auto whitespace-pre-wrap break-words rounded-lg bg-muted p-3 font-sans text-sm">{c.evidence}</pre></details>
    <div className="grid gap-1"><h4 className="text-sm font-semibold">What counts as a pass</h4><p className="text-sm">{c.pass_criteria}</p></div>
    <form className="grid gap-4" onSubmit={async (e) => {
      e.preventDefault()
      if (!verdict) { setError("Choose a verdict first."); return }
      setBusy(true); setError("")
      try { await onSave(verdict, note) } finally { setBusy(false) }
    }}>
      <fieldset disabled={busy} className="flex flex-wrap gap-2"><legend className="mb-2 text-sm font-medium">Your verdict</legend>{c.verdicts.map((v) =>
        <label key={v} className="relative flex min-h-11 cursor-pointer items-center gap-2 px-4"><input className="absolute inset-0 h-full w-full cursor-pointer appearance-none rounded-lg border border-border checked:border-primary checked:bg-secondary focus-visible:outline-2 focus-visible:outline-ring" type="radio" name="phone-verdict" value={v} checked={verdict === v} onChange={() => { setVerdict(v); setError("") }} /><span aria-hidden="true" className={`pointer-events-none relative size-3 rounded-full border border-foreground ${verdict === v ? "bg-foreground" : ""}`} /><span className="pointer-events-none relative">{v}</span></label>)}</fieldset>
      <div className="grid gap-2"><label htmlFor="phone-note" className="text-sm font-medium">Note (optional)</label>
        <Textarea id="phone-note" className="min-h-24 text-base" value={note} maxLength={4000} disabled={busy} onChange={(e) => setNote(e.target.value)} /></div>
      {error && <p role="alert" className="text-sm text-(--destructive-text)">{error}</p>}
      <div className="flex flex-wrap gap-2"><Button type="submit" disabled={busy}>Save answer</Button><Button type="button" variant="outline" disabled={busy} onClick={onSkip}>Skip today</Button></div>
    </form>
  </article>
}

function ReminderSettings() {
  const [s, setS] = useState(() => reminders.load(storage.get))
  const [message, setMessage] = useState("")
  if (!reminders.available()) return null
  return <details className="mobile-paper"><summary className="min-h-11 cursor-pointer py-3 text-sm font-medium">Reminders: {s.on ? s.times.join(", ") : "off"}</summary>
    <form className="mt-3 grid gap-3" onSubmit={async (e) => { e.preventDefault(); try { setMessage(await reminders.apply(s, storage.set)); setS(reminders.load(storage.get)) } catch { setMessage("Could not set reminders on this phone.") } }}>
      <label className="flex min-h-11 items-center gap-3 text-sm"><input type="checkbox" className="size-5" checked={s.on} onChange={(e) => setS({ ...s, on: e.target.checked })} />Remind me each day</label>
      {s.times.map((t, i) => <label key={i} className="grid gap-1 text-sm">Time {i + 1}<input type="time" className="min-h-11 rounded-lg border border-border bg-card px-3" value={t} onChange={(e) => setS({ ...s, times: s.times.map((x, n) => n === i ? e.target.value : x) })} /></label>)}
      <div className="flex flex-wrap gap-2">
        {s.times.length < reminders.MAX_TIMES && <Button type="button" variant="outline" onClick={() => setS({ ...s, times: [...s.times, "18:00"] })}>Add time</Button>}
        {s.times.length > 1 && <Button type="button" variant="outline" onClick={() => setS({ ...s, times: s.times.slice(0, -1) })}>Remove last</Button>}
        <Button type="submit">Save</Button>
      </div>
      {message && <p role="status" className="text-sm">{message}</p>}
    </form>
  </details>
}
