import { useEffect, useState } from "react"
import { useStatus } from "@/App"
import {
  Empty, Evidence, ExternalLink, Facts, FeedbackSelect, FreshnessPill, ListDetail, ListItem, LOCATION_TONE, MatchPill, ModelNote, PageHeader, Pill, RunHistoryLink, Section,
} from "@/components/common"
import { ArrowClockwiseIcon, PlusIcon, WarningIcon } from "@/components/icons"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { NativeSelect } from "@/components/ui/native-select"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Textarea } from "@/components/ui/textarea"
import { api, useApi, type Analysis, type JobFit, type JobRow, type TaskRef } from "@/lib/api"
import { ago, day, when } from "@/lib/format"
import { go, href, useRoute } from "@/lib/router"

const VIEWS: [string, string][] = [["matches", "Matches"], ["review", "To review"], ["saved", "Shortlist"], ["outside", "Outside preferences"], ["closed", "No longer listed"]]

interface JobList { jobs: JobRow[]; counts: Record<string, number>; statuses: string[]; locationLabels: Record<string, string> }
interface JobDetail extends JobRow {
  description_text: string; official_url: string | null; apply_url: string | null; salary_kind: string | null; location_evidence: string;
  workplace_raw: string | null; role_family: string; closed_at: string | null; changed_at: string | null; ext_id: string;
  company: { name: string; careers_url: string; verification: string; last_success_at: string | null; last_error: string | null } | null
  versions: { id: number; title: string; location_raw: string; salary_text: string | null; seen_at: string }[]
  duplicates: { id: number; title: string; official_url: string }[]
  fit: Analysis<JobFit> | null; task: TaskRef | null; compensation_note: string; location_label: string; family_label: string
  feedback: string[]; profile_facts: { id: string; text: string }[]
}

export default function Jobs() {
  const route = useRoute()
  const view = route.params.get("view") ?? "matches"
  const [q, setQ] = useState(route.params.get("q") ?? "")
  const [status, setStatus] = useState("")
  const [location, setLocation] = useState("")
  const [sort, setSort] = useState("first_seen")
  const [importing, setImporting] = useState(false)
  const query = new URLSearchParams({ view, q, status, location, sort }).toString()
  const { data, error, reload } = useApi<JobList>(`/api/jobs?${query}`)
  const { status: st } = useStatus()
  useEffect(() => { reload() }, [st?.counts.matches, st?.queue.queued]) // eslint-disable-line react-hooks/exhaustive-deps

  const link = (id?: number) => href("jobs", id, { view })
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-8 p-4 sm:p-6">
      <PageHeader title="Jobs" line="From employers' own job boards. Apply on their sites; SignalDesk never applies or messages anyone."
        action={<><RunHistoryLink agent="job_scout" label="Job Scout" /><Button variant="outline" onClick={() => setImporting(true)}><PlusIcon className="size-4" />Add a job by hand</Button></>} />
      <div className="flex flex-col gap-4">
        <Tabs value={view} onValueChange={(v) => go("jobs", null, { view: String(v) })}>
          <TabsList className="flex-wrap">
            {VIEWS.map(([v, label]) => <TabsTrigger key={v} value={v}>{label}{data ? ` (${data.counts[v] ?? 0})` : ""}</TabsTrigger>)}
          </TabsList>
        </Tabs>
        <div className="flex flex-wrap items-end gap-3" role="search">
          <div className="flex w-full flex-col gap-1 sm:w-64"><Label htmlFor="job-q">Search</Label>
            <Input id="job-q" type="search" placeholder="Title, employer or text" value={q} onChange={(e) => setQ(e.target.value)} /></div>
          <div className="flex w-40 flex-col gap-1"><Label htmlFor="job-status">Status</Label>
            <NativeSelect id="job-status" value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">Any active</option>{data?.statuses.map((s) => <option key={s}>{s}</option>)}
            </NativeSelect></div>
          <div className="flex w-52 flex-col gap-1"><Label htmlFor="job-loc">Location</Label>
            <NativeSelect id="job-loc" value={location} onChange={(e) => setLocation(e.target.value)}>
              <option value="">Any</option>{data && Object.entries(data.locationLabels).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </NativeSelect></div>
          <div className="flex w-44 flex-col gap-1"><Label htmlFor="job-sort">Sort by</Label>
            <NativeSelect id="job-sort" value={sort} onChange={(e) => setSort(e.target.value)}>
              <option value="first_seen">First seen</option><option value="published">Published</option><option value="employer">Employer</option><option value="title">Title</option>
            </NativeSelect></div>
        </div>
      </div>
      <ListDetail hasSelection={!!route.id} backHref={link()}
        list={
          <>
            <p className="border-b border-border px-4 py-2 text-xs text-muted-foreground" aria-live="polite">{data ? `${data.jobs.length} shown` : error ?? "Loading"}</p>
            {data && !data.jobs.length ? (
              <Empty title="No jobs here" line={view === "matches" ? "Nothing matches your role and location preferences yet. Run the Job Scout from Today, or look at To review." : "Nothing in this view with these filters."} />
            ) : (
              <ul className="min-h-0 flex-1 overflow-y-auto">
                {data?.jobs.map((j) => (
                  <ListItem key={j.id} selected={route.id === j.id} to={link(j.id)}>
                    <span className="font-medium leading-snug">{j.title}</span>
                    <span className="text-sm text-muted-foreground">{j.employer} · {j.location_raw || "location not stated"}</span>
                    <span className="flex flex-wrap gap-1.5 pt-0.5">
                      {view !== "outside" && view !== "closed" && <MatchPill match={j.match} pending={j.analysis_pending} />}
                      {j.change_state !== "unchanged" && j.listing_state === "open" && <Pill>{j.change_state === "new" ? "New" : "Changed"}</Pill>}
                      {j.status !== "New" && <Pill>{j.status}</Pill>}
                      {view === "review" && <Pill tone="warning">{j.bucket_reason.replace(/^Check: /, "")}</Pill>}
                      {view === "outside" && <Pill>{j.bucket_reason}</Pill>}
                    </span>
                  </ListItem>
                ))}
              </ul>
            )}
          </>
        }
        detail={route.id ? <JobView id={route.id} statuses={data?.statuses ?? []} onChange={reload} /> : <Empty title="Select a job" line="Its fit analysis, evidence and the original description open here." />} />
      <ImportDialog open={importing} onOpenChange={setImporting} onDone={(id) => { reload(); go("jobs", id, { view: "matches" }) }} />
    </div>
  )
}

function JobView({ id, statuses, onChange }: { id: number; statuses: string[]; onChange: () => void }) {
  const { data: j, reload } = useApi<JobDetail>(`/api/jobs/${id}`)
  const [note, setNote] = useState<string | null>(null)
  useEffect(() => {
    if (!j?.task || !["queued", "running"].includes(j.task.status)) return
    const t = window.setInterval(reload, 4000)
    return () => window.clearInterval(t)
  }, [j?.task, reload])
  useEffect(() => setNote(null), [id])
  if (!j) return <p className="p-6 text-sm text-muted-foreground">Loading</p>

  const setStatus = async (s: string) => { await api.send(`/api/jobs/${id}`, "PATCH", { status: s }); reload(); onChange() }
  const analyse = async () => { const r = await api.send<{ result: string }>(`/api/jobs/${id}/analyse`, "POST"); setNote(r.result === "cached" ? "A saved analysis for this exact text and profile already exists." : "Queued for the local model."); reload() }
  const recheck = async () => { setNote("Checking the employer's board"); const r = await api.send<{ result: string }>(`/api/jobs/${id}/recheck`, "POST"); setNote(r.result); reload(); onChange() }
  const fit = j.fit?.output
  // Show the fact text the model actually saw. Ids are renumbered when the profile
  // changes, so an outdated result without a snapshot can't be resolved safely.
  const sent = j.fit?.inputs.facts_sent
  const facts: Record<string, string> = Object.fromEntries((sent ?? (j.fit?.outdated ? [] : j.profile_facts)).map((f) => [f.id, f.text]))
  const missingFact = sent || !j.fit?.outdated ? "Fact no longer in your profile" : "Your profile changed since this analysis; the cited fact text wasn't recorded. Re-analyse to see it."
  const waiting = j.task && ["queued", "running"].includes(j.task.status)

  return (
    <article className="flex flex-col gap-6 p-5" aria-labelledby="job-title">
      <header className="flex flex-col gap-2">
        <h2 id="job-title" className="font-heading text-2xl font-medium leading-tight">{j.title}</h2>
        <p className="text-sm text-muted-foreground">{j.employer} · {j.location_raw || "location not stated"}</p>
        <div className="flex flex-wrap gap-1.5">
          <MatchPill match={fit?.match} pending={!!waiting} />
          <Pill tone={LOCATION_TONE[j.location_class] ?? "neutral"}>{j.location_label}</Pill>
          {j.listing_state === "open" ? <FreshnessPill hours={j.verified_hours_ago} /> : <Pill tone="danger">No longer listed since {day(j.closed_at)}</Pill>}
          {j.change_state === "changed" && <Pill>Changed {ago(j.changed_at)}</Pill>}
          {!!j.injection_flag && <Pill tone="warning" title="The text contains wording aimed at AI tools. It was treated as data and ignored.">Contains instructions aimed at AI</Pill>}
        </div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 pt-1">
          <ExternalLink url={j.apply_url}>Apply on the employer's site</ExternalLink>
          {j.official_url !== j.apply_url && <ExternalLink url={j.official_url}>Original listing</ExternalLink>}
        </div>
      </header>

      <div className="flex flex-wrap items-end gap-3">
        <div className="flex w-44 flex-col gap-1"><Label htmlFor="status">Your status</Label>
          <NativeSelect id="status" value={j.status} onChange={(e) => setStatus(e.target.value)}>{statuses.map((s) => <option key={s}>{s}</option>)}</NativeSelect></div>
        <Button variant="outline" onClick={analyse} disabled={!!waiting}>{fit ? (j.fit!.outdated ? "Re-analyse (outdated)" : "Analyse again") : "Analyse fit"}</Button>
        <Button variant="ghost" onClick={recheck}><ArrowClockwiseIcon className="size-4" />Recheck listing</Button>
      </div>
      {note && <p role="status" className="text-sm text-muted-foreground">{note}</p>}
      {j.task?.status === "failed" && <p className="text-sm text-(--destructive-text)">The last analysis failed: {j.task.error}</p>}
      {waiting && <p className="text-sm text-muted-foreground">Analysis {j.task!.status === "running" ? "running now" : "queued"}{j.task!.note ? `: ${j.task!.note}` : ""}.</p>}

      <div className="grid grid-cols-1 gap-8 xl:grid-cols-[minmax(0,1fr)_18rem]">
        <div className="flex min-w-0 flex-col gap-6">
          {fit ? (
            <>
              <Section title="Fit">
                <p className="max-w-[70ch]">{fit.summary !== "unknown" ? fit.summary : "The model gave no summary."}</p>
                <p className="text-sm text-muted-foreground">A potential match is not confirmed eligibility: check location and work authorisation on the listing.</p>
                <ModelNote model={j.fit!.model_id} at={j.fit!.created_at} version={j.fit!.prompt_version} notes={j.fit!.validation.notes} coverage={j.fit!.inputs.coverage} />
                {j.fit!.outdated && <p className="text-sm text-(--warning-text)">Outdated: the text, your profile, the prompt or the model settings changed since. Run it again for a current result.</p>}
              </Section>
              <Requirements title="Essential requirements" items={fit.essential} />
              <Requirements title="Preferred" items={fit.preferred} />
              <Section title="Your evidence">
                {fit.evidence.length ? (
                  <ul className="flex flex-col gap-3">{fit.evidence.map((e) => (
                    <li key={e.req} className="grid gap-2 md:grid-cols-2">
                      <div><p className="font-medium">{e.req}</p><p className="text-sm text-muted-foreground">{e.note}</p></div>
                      <ul className="flex flex-col gap-1 text-sm">{e.facts.map((f) => <li key={f} className="rounded-md bg-muted px-3 py-1.5"><span className="text-muted-foreground">{f}</span> {facts[f] ?? missingFact}</li>)}</ul>
                    </li>))}</ul>
                ) : <p className="text-sm text-muted-foreground">No requirement was tied to a fact in your profile.</p>}
              </Section>
              <div className="grid gap-6 md:grid-cols-2">
                <Section title="Gaps">{fit.gaps.length ? <ul className="list-disc ps-5 text-sm">{fit.gaps.map((g) => <li key={g}>{g}</li>)}</ul> : <p className="text-sm text-muted-foreground">None named.</p>}</Section>
                <Section title="Unknowns">{fit.unknowns.length ? <ul className="list-disc ps-5 text-sm">{fit.unknowns.map((g) => <li key={g}>{g}</li>)}</ul> : <p className="text-sm text-muted-foreground">None named.</p>}</Section>
              </div>
            </>
          ) : (
            <Section title="Fit"><p className="text-sm text-muted-foreground">{waiting ? "Waiting for the local model." : "Not analysed yet. The listing details on the right come from the employer's board and rules, not the model."}</p></Section>
          )}
          <Section title="Original description">
            <div className="max-h-[32rem] max-w-[72ch] overflow-y-auto whitespace-pre-wrap rounded-lg border border-border p-4 text-[0.95rem] leading-relaxed" tabIndex={0} aria-label="Original job description">
              {j.description_text || "The board gave no description."}
            </div>
          </Section>
          {!!j.versions.length && (
            <Section title="Earlier versions">
              <ul className="text-sm">{j.versions.map((v) => <li key={v.id}>{when(v.seen_at)}: {v.title} · {v.location_raw}{v.salary_text ? ` · ${v.salary_text}` : ""}</li>)}</ul>
            </Section>
          )}
        </div>
        <aside className="flex flex-col gap-5 text-sm" aria-label="Listing facts">
          <Facts rows={[
            ["Pay as written", j.salary_text ?? "Not disclosed"],
            ["Pay type", j.salary_text ? j.salary_kind : null],
            ["Against ₹ preference", j.compensation_note],
            ["Location as written", j.location_evidence || j.location_raw || "Not stated"],
            ["Workplace", j.workplace_raw],
            ["Role family", j.family_label],
            ["Why in this list", j.bucket_reason],
            ["Published", j.published_at ? day(j.published_at) : "Not stated by the source"],
            ["First seen", day(j.first_seen_at)],
            ["Last verified", j.last_verified_at ? when(j.last_verified_at) : "Never"],
            ["Source", j.company ? `${j.source} board` : "Added by hand"],
          ]} />
          {j.company && <p className="text-xs text-muted-foreground">Board check: {j.company.verification}</p>}
          {!!j.duplicates.length && <p className="text-xs text-muted-foreground">{j.duplicates.length} duplicate listing(s) of this role are hidden.</p>}
          <div className="flex flex-col gap-2"><span className="font-medium">Use in briefings</span><FeedbackSelect type="job" id={j.id} value={j.feedback[0] ?? ""} onChange={() => reload()} /></div>
        </aside>
      </div>
    </article>
  )
}

function Requirements({ title, items }: { title: string; items: JobFit["essential"] }) {
  return (
    <Section title={title}>
      {items.length ? (
        <ul className="flex flex-col gap-3">{items.map((r) => (
          <li key={r.req + r.quote} className="grid gap-2 md:grid-cols-2">
            <p className="flex items-start gap-1.5">{!r.quote_found && <WarningIcon className="mt-1 size-3.5 shrink-0 text-(--warning-text)" aria-label="Quote not found" />}{r.req}</p>
            <Evidence quote={r.quote} found={r.quote_found} />
          </li>))}</ul>
      ) : <p className="text-sm text-muted-foreground">None identified.</p>}
    </Section>
  )
}

function ImportDialog({ open, onOpenChange, onDone }: { open: boolean; onOpenChange: (o: boolean) => void; onDone: (id: number) => void }) {
  const [form, setForm] = useState({ url: "", title: "", employer: "", location: "", text: "", apply_url: "" })
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value })
  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const r = await api.send<{ id: number }>("/api/jobs/import", "POST", form)
      onOpenChange(false)
      setForm({ url: "", title: "", employer: "", location: "", text: "", apply_url: "" })
      onDone(r.id)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl">
        <form onSubmit={submit} className="flex flex-col gap-4">
          <DialogHeader>
            <DialogTitle>Add a job by hand</DialogTitle>
            <DialogDescription>For listings from LinkedIn or anywhere else: paste the text yourself. With only a link, SignalDesk reads the public page if its robots.txt allows.</DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-1"><Label htmlFor="imp-url">Original job URL (required)</Label><Input id="imp-url" required type="url" value={form.url} onChange={set("url")} /></div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="flex flex-col gap-1"><Label htmlFor="imp-title">Title</Label><Input id="imp-title" value={form.title} onChange={set("title")} /></div>
            <div className="flex flex-col gap-1"><Label htmlFor="imp-emp">Employer</Label><Input id="imp-emp" value={form.employer} onChange={set("employer")} /></div>
            <div className="flex flex-col gap-1"><Label htmlFor="imp-loc">Location as written</Label><Input id="imp-loc" value={form.location} onChange={set("location")} /></div>
            <div className="flex flex-col gap-1"><Label htmlFor="imp-apply">Application URL</Label><Input id="imp-apply" type="url" value={form.apply_url} onChange={set("apply_url")} /></div>
          </div>
          <div className="flex flex-col gap-1"><Label htmlFor="imp-text">Job description</Label><Textarea id="imp-text" rows={6} value={form.text} onChange={set("text")} /></div>
          {error && <p role="alert" className="text-sm text-(--destructive-text)">{error}</p>}
          <DialogFooter><Button type="submit" disabled={busy}>{busy ? "Adding" : "Add job"}</Button></DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
