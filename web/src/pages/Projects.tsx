import { useRef, useState } from "react"
import { Empty, PageHeader, Section } from "@/components/common"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { api, useApi } from "@/lib/api"
import { day, plural } from "@/lib/format"

interface Task {
  id: string; project: string; type: string; title: string; text: string; evidence: string
  pass_criteria: string; what_this_is: string; why_it_matters: string; unlocks_next: string
  verdicts: string[]; skipped_at: string | null
  why_sources?: { kind: "readme" | "count"; text: string; source?: string; file?: string; line?: number }[]
  response: { verdict: string; note: string; at: string; input_origin: "human" } | null
}
interface Project {
  name: string; kind: string; available: boolean; open_reviews: number; branch: string | null
  last_commit_at: string | null; dirty: boolean | null; git_error: string | null; notice: string | null
}
interface Batch {
  day: string; prepared: boolean; tasks: Task[]; reminders: Task[]; projects: Project[]
  done_this_week: Record<string, number>
}

export default function Projects() {
  const { data, error, reload, setData } = useApi<Batch>("/api/projects")
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState("")
  const [message, setMessage] = useState("")
  const [exportError, setExportError] = useState("")
  const [active, setActive] = useState<string | null>(null)
  const heading = useRef<HTMLHeadingElement>(null)
  async function collect() {
    setBusy(true); setFailure(""); setMessage("")
    try { setData(await api.send<Batch>("/api/projects/collect", "POST", {})) }
    catch (e) { setFailure(e instanceof Error ? e.message : String(e)) }
    finally { setBusy(false) }
  }
  async function exportAnswers() {
    setBusy(true); setExportError(""); setMessage("")
    try {
      const result = await api.send<{ directory: string; files: string[] }>("/api/projects/export", "POST", {})
      setMessage(`Exported ${result.files.length} project files to ${result.directory}`)
    } catch (e) { setExportError(e instanceof Error ? e.message : String(e)) }
    finally { setBusy(false) }
  }
  const pending = data?.tasks.filter(t => !t.response && !t.skipped_at) ?? []
  const task = pending.find(t => t.id === active) ?? pending[0]
  const done = data?.tasks.filter(t => t.response).length ?? 0
  async function changed() { setActive(null); await reload(); heading.current?.focus() }
  return <div className="flex flex-col gap-8 p-4 sm:p-6">
    <PageHeader title="Projects" line="Project Coach chooses up to three reviews a day. Your answers stay in SignalDesk until you export them."
      action={<Button className="min-h-11" variant="outline" onClick={collect} disabled={busy}>{busy ? "Preparing…" : data?.prepared ? "Reload today's batch" : "Prepare today's tasks"}</Button>} />
    {(error || failure) && <p role="alert" className="text-sm text-(--destructive-text)">{failure || error}</p>}
    <p role="status" className="break-words text-sm text-muted-foreground">{(data ? `${done} of ${data.tasks.length} reviews answered today. Explanations use fixed templates; no model is needed.` : "Loading projects…")}</p>
    {data && !data.prepared && <Empty title="Your daily batch is not prepared yet" line="Prepare today's tasks to read the configured clones. Add [[project]] entries in the data folder's config.toml first." />}
    {data?.prepared && <>
      <section className="flex max-w-3xl flex-col gap-4" aria-labelledby="review-heading">
        <h2 id="review-heading" ref={heading} tabIndex={-1} className="text-base font-semibold focus:outline-none">Today's tasks</h2>
        {task ? <>
          <nav aria-label="Today's review tasks" className="flex flex-wrap gap-2">{pending.map((t, i) =>
            <Button key={t.id} className="min-h-11" variant={t.id === task.id ? "secondary" : "outline"} aria-current={t.id === task.id ? "step" : undefined} onClick={() => setActive(t.id)}>{i + 1}. {t.project}</Button>)}</nav>
          <Review key={task.id} task={task} changed={changed} />
        </> : <Empty title={data.tasks.length ? "No more reviews today" : "No reviews ready today"} line="Check the laptop list and project status below. Answering or skipping a task does not add another task to today's allowance." />}
      </section>
      <Section title="Laptop list">
        {data.reminders.length ? <ul className="flex max-w-3xl flex-col gap-4">{data.reminders.map(t => <li key={t.id} className="flex flex-col gap-2 rounded-lg border border-border p-4">
          <h3 className="font-semibold">{t.project} · Read only</h3><p className="whitespace-pre-wrap text-sm">{t.text}</p>
          <p className="text-sm text-muted-foreground">{t.why_it_matters}</p>
        </li>)}</ul> : <p className="text-sm text-muted-foreground">No laptop reminders in today's batch.</p>}
      </Section>
      <Section title="Project status">
        <ul className="flex max-w-3xl flex-col divide-y divide-border">{data.projects.map(p => <li key={p.name} className="flex flex-col gap-2 py-4">
          <h3 className="font-semibold">{p.name}</h3>
          <p className="text-sm">{plural(data.done_this_week[p.name] ?? 0, "review")} done this week · {p.open_reviews} open at collection</p>
          <p className="break-words text-sm text-muted-foreground">Branch: {p.branch ?? "unknown"} · Last commit: {day(p.last_commit_at)} · {p.dirty === null ? "Uncommitted work unknown" : p.dirty ? "Has uncommitted work" : "No uncommitted work"}</p>
          {(p.notice || p.git_error) && <p className="text-sm text-(--warning-text)">{p.notice || p.git_error}</p>}
        </li>)}</ul>
        {!data.projects.length && <p className="text-sm">No projects configured. Add [[project]] entries to config.toml and restart. They will be collected in the next daily batch.</p>}
      </Section>
      <Section title="Your answers">
        <p className="max-w-3xl text-sm text-muted-foreground">Exports go to the data folder. Importing them into another project remains a separate laptop action.</p>
        <div><Button className="min-h-11" variant="outline" disabled={busy} onClick={exportAnswers}>Export saved answers</Button></div>
        {message && <p role="status" className="max-w-3xl break-words text-sm">{message}</p>}
        {exportError && <p role="alert" className="max-w-3xl break-words text-sm text-(--destructive-text)">{exportError}</p>}
        {data.tasks.filter(t => t.response).map(t => <p key={t.id} className="text-sm">{t.project}: {t.response!.verdict} · Human input · {day(t.response!.at)}</p>)}
      </Section>
    </>}
  </div>
}

function Review({ task: t, changed }: { task: Task; changed: () => Promise<void> }) {
  const [verdict, setVerdict] = useState("")
  const [note, setNote] = useState("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  async function save(skip = false) {
    if (!skip && !verdict) { setError("Choose a verdict before saving."); return }
    setBusy(true); setError("")
    try {
      await api.send(`/api/projects/tasks/${t.id}/${skip ? "skip" : "response"}`, "POST", skip ? {} : { verdict, note })
      await changed()
    } catch (e) { setError(e instanceof Error ? e.message : String(e)) }
    finally { setBusy(false) }
  }
  return <article className="flex min-w-0 flex-col gap-6 rounded-lg border border-border p-4 sm:p-6">
    <div className="flex flex-col gap-2"><p className="text-sm text-muted-foreground">{t.project}</p><h3 className="text-lg font-semibold">{t.title}</h3></div>
    <div className="flex flex-col gap-2"><h4 className="font-semibold">What this is</h4><p className="text-sm">{t.what_this_is}</p></div>
    <div className="flex flex-col gap-2"><h4 className="font-semibold">Why it matters</h4><p className="text-sm">{t.why_it_matters}</p>
      {!!t.why_sources?.length && <p className="text-xs text-muted-foreground">Sources: {t.why_sources.map(f => f.kind === "readme" ? `${t.project} ${f.file} line ${f.line}` : f.source).join(" · ")}</p>}</div>
    <div className="flex flex-col gap-2"><h4 className="font-semibold">What it unlocks next</h4><p className="text-sm">{t.unlocks_next}</p></div>
    <div className="flex flex-col gap-2"><h4 className="font-semibold">Text to judge</h4><p className="whitespace-pre-wrap break-words text-sm leading-relaxed">{t.text}</p></div>
    <details className="min-w-0"><summary className="min-h-11 cursor-pointer py-3 font-medium focus-visible:outline-2 focus-visible:outline-ring">Read the source and engine facts</summary><pre className="max-h-[32rem] overflow-y-auto whitespace-pre-wrap break-words rounded-md bg-muted p-4 font-sans text-sm">{t.evidence}</pre></details>
    <div className="flex flex-col gap-2"><h4 className="font-semibold">What counts as a pass</h4><p className="text-sm">{t.pass_criteria}</p></div>
    <form className="flex flex-col gap-4" onSubmit={e => { e.preventDefault(); void save() }}>
      <fieldset disabled={busy} className="flex flex-wrap gap-2"><legend className="mb-2 text-sm font-medium">Your verdict</legend>{t.verdicts.map(v =>
        <label key={v} className="relative flex min-h-11 cursor-pointer items-center gap-2 px-4 text-base"><input className="absolute inset-0 h-full w-full cursor-pointer appearance-none rounded-md border border-border checked:border-primary checked:bg-secondary focus-visible:outline-2 focus-visible:outline-ring" type="radio" name="verdict" value={v} checked={verdict === v} onChange={() => { setVerdict(v); setError("") }} /><span aria-hidden="true" className={`pointer-events-none relative size-3 rounded-full border border-foreground ${verdict === v ? "bg-foreground" : ""}`} /><span className="pointer-events-none relative">{v}</span></label>)}</fieldset>
      <div className="flex flex-col gap-2"><label className="text-sm font-medium" htmlFor="project-note">Your note (optional)</label>
        <Textarea id="project-note" className="min-h-24 resize-y text-base" value={note} maxLength={4000} disabled={busy} onChange={e => setNote(e.target.value)} onKeyDown={e => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); void save() } }} /></div>
      {error && <p role="alert" className="text-sm text-(--destructive-text)">{error}</p>}
      <div className="flex flex-wrap gap-2"><Button className="min-h-11" type="submit" disabled={busy}>{busy ? "Saving…" : "Save human verdict"}</Button><Button className="min-h-11" type="button" variant="outline" disabled={busy} onClick={() => void save(true)}>Skip today</Button></div>
    </form>
  </article>
}
