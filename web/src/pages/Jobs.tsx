import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react"
import { useStatus } from "@/App"
import {
  Empty, Evidence, ExternalLink, Facts, FeedbackSelect, FreshnessPill, ListDetail, ListItem, LOCATION_TONE, MatchPill, ModelNote, PageHeader, Pill, RunHistoryLink, Section,
} from "@/components/common"
import { ArrowClockwiseIcon, ArrowSquareOutIcon, BookmarkSimpleIcon, CheckCircleIcon, PlusIcon, WarningIcon, XIcon } from "@/components/icons"
import { ContactCard } from "@/components/outreach"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { NativeSelect } from "@/components/ui/native-select"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Textarea } from "@/components/ui/textarea"
import { api, useApi, type Analysis, type Contact, type FundingEvent, type JobFit, type JobRow, type TaskRef, type Tone } from "@/lib/api"
import { ago, day, ROUND_LABEL, SOURCE_LABEL, when } from "@/lib/format"
import { go, href, useRoute } from "@/lib/router"
import { cn } from "@/lib/utils"

const PRIMARY_VIEWS: [string, string][] = [["matches", "Matches"], ["review", "To review"], ["saved", "Shortlist"]]
const OTHER_VIEWS: [string, string][] = [["outside", "Outside preferences"], ["closed", "No longer listed"]]
const VIEW_NOUN: Record<string, string> = { matches: "matches", review: "jobs to review", saved: "shortlisted jobs", outside: "jobs outside your preferences", closed: "listings no longer listed" }
const SORTS: Record<string, string> = { first_seen: "First seen", published: "Published", employer: "Employer", title: "Title" }
const UNCERTAIN = new Set(["remote_unclear", "india_unspecified", "unknown"])
const CITY = /\b(bengaluru|bangalore|mumbai|delhi|new delhi|gurugram|gurgaon|noida|hyderabad|pune|chennai|kolkata|ahmedabad)\b/gi
const SHORTLISTED = ["Interested", "Investigate"]

interface JobList {
  jobs: (JobRow & { workplace_raw: string | null })[]; counts: Record<string, number>; statuses: string[]; locationLabels: Record<string, string>
  families: Record<string, string>; bands: Record<string, string>; groups: Record<string, string>
}
const BAND_TONE: Record<string, Tone> = { above: "success", overlaps: "neutral", below: "warning", unknown: "neutral" }
interface JobDetail extends JobRow {
  found_on: { source: string; url: string; first_seen_at: string; last_seen_at: string }[]
  contacts: Contact[]
  funding: { startup_id: number; name: string; india_link: string; india_evidence: string | null; latest: FundingEvent | null; days_since: number | null } | null
  role_evidence_list: string[]
  description_text: string; official_url: string | null; apply_url: string | null; salary_kind: string | null; location_evidence: string;
  workplace_raw: string | null; role_family: string; closed_at: string | null; changed_at: string | null; ext_id: string;
  company: { name: string; careers_url: string; verification: string; last_success_at: string | null; last_error: string | null } | null
  versions: { id: number; title: string; location_raw: string; salary_text: string | null; seen_at: string }[]
  duplicates: { id: number; title: string; official_url: string }[]
  fit: Analysis<JobFit> | null; task: TaskRef | null; compensation_note: string; location_label: string; family_label: string
  feedback: string[]; profile_facts: { id: string; text: string }[]
}

/** Work arrangement and city count, read from the listing's own wording. */
function arrangement(j: { location_raw: string | null; workplace_raw?: string | null; location_class: string }) {
  const text = `${j.location_raw ?? ""} ${j.workplace_raw ?? ""}`
  const cities = new Set((text.match(CITY) ?? []).map((c) => c.toLowerCase().replace("bangalore", "bengaluru").replace("gurgaon", "gurugram")))
  return {
    hybrid: /hybrid/i.test(text), remote: j.location_class.startsWith("remote") || /\bremote\b/i.test(text),
    onsite: /on-?site|in office/i.test(text), multiCity: cities.size > 1,
  }
}

// Filters live in the link, so a reload, the back button and "Back to results" restore them.
const FILTER_KEYS = ["q", "locgroup", "family", "status", "comp", "sort"] as const
type Filters = Record<(typeof FILTER_KEYS)[number], string>

export default function Jobs() {
  const route = useRoute()
  const view = route.params.get("view") ?? "matches"
  const fromLink = () => Object.fromEntries(FILTER_KEYS.map((k) => [k, route.params.get(k) ?? ""])) as Filters
  const linkKey = FILTER_KEYS.map((k) => route.params.get(k) ?? "").join("\u0000")
  const [f, setF] = useState<Filters>(fromLink)
  // A link or the back button changed the filters while this page stayed open: follow the link.
  const [seenKey, setSeenKey] = useState(linkKey)
  if (seenKey !== linkKey) { setSeenKey(linkKey); setF(fromLink()) }
  const [importing, setImporting] = useState(false)
  const params = useMemo(() => Object.fromEntries(Object.entries({ view: view === "matches" ? "" : view, ...f }).filter(([, v]) => v)), [view, f])
  const query = new URLSearchParams({ view, ...f, sort: f.sort || "first_seen" }).toString()
  const { data, error, reload } = useApi<JobList>(`/api/jobs?${query}`)
  const { status: st } = useStatus()
  useEffect(() => { reload() }, [st?.counts.matches, st?.queue.queued]) // eslint-disable-line react-hooks/exhaustive-deps

  const set = (k: keyof Filters, v: string) => {
    const next = { ...f, [k]: v }
    setF(next)
    const p = Object.fromEntries(Object.entries({ view: view === "matches" ? "" : view, ...next }).filter(([, x]) => x))
    window.history.replaceState(null, "", href("jobs", route.id, p))   // update the link without a history entry per keystroke
  }
  const clearAll = () => { const empty = Object.fromEntries(FILTER_KEYS.map((k) => [k, ""])) as Filters; setF(empty); window.history.replaceState(null, "", href("jobs", route.id, view === "matches" ? {} : { view })) }
  const link = (id?: number | null) => href("jobs", id ?? null, params)

  // Keep the list's scroll position when a job opens full-screen on a phone and you come back.
  const listRef = useRef<HTMLUListElement>(null)
  const remember = () => {
    try { sessionStorage.setItem(`jobs-scroll:${query}`, JSON.stringify({ list: listRef.current?.scrollTop ?? 0, page: document.getElementById("main")?.scrollTop ?? 0 })) } catch { /* not stored */ }
  }
  useLayoutEffect(() => {
    if (route.id || !data) return
    try {
      const saved = JSON.parse(sessionStorage.getItem(`jobs-scroll:${query}`) ?? "null")
      if (saved) { if (listRef.current) listRef.current.scrollTop = saved.list; const main = document.getElementById("main"); if (main) main.scrollTop = saved.page }
    } catch { /* nothing to restore */ }
  }, [route.id, data, query])

  const jobs = data?.jobs ?? []
  const allNew = jobs.length > 0 && jobs.every((j) => j.change_state === "new")
  const oneLocation = jobs.length > 0 && jobs.every((j) => j.location_class === jobs[0].location_class)
  const total = data?.counts[view] ?? 0
  const activeChips = [
    f.q && { k: "q" as const, text: `“${f.q}”` },
    f.locgroup && { k: "locgroup" as const, text: data?.groups[f.locgroup] ?? f.locgroup },
    f.family && { k: "family" as const, text: data?.families[f.family] ?? f.family },
    f.status && { k: "status" as const, text: `Status: ${f.status}` },
    f.comp && { k: "comp" as const, text: data?.bands[f.comp] ?? f.comp },
  ].filter(Boolean) as { k: keyof Filters; text: string }[]
  const moreActive = [f.status, f.comp, f.sort && f.sort !== "first_seen"].filter(Boolean).length
  const otherView = OTHER_VIEWS.find(([v]) => v === view)

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-5 p-4 sm:p-6">
      {/* On a phone an open job takes the whole screen; "Back to results" returns to these filters. */}
      <div className={cn("flex flex-col gap-5", route.id && "hidden lg:flex")}>
      <PageHeader sans title={otherView ? otherView[1] : "Jobs"} line={otherView ? <a className="text-(--primary-text) underline underline-offset-2" href={href("jobs")}>Back to Matches</a> : "Roles from employers' own job boards. You apply on their sites."}
        action={<><RunHistoryLink agent="job_scout" label="Job Scout" /><Button variant="outline" onClick={() => setImporting(true)}><PlusIcon className="size-4" />Add a job by hand</Button></>} />

      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <Tabs value={otherView ? "" : view} onValueChange={(v) => go("jobs", null, { ...params, view: String(v) === "matches" ? "" : String(v) })}>
            <TabsList aria-label="Job lists">
              {PRIMARY_VIEWS.map(([v, label]) => <TabsTrigger key={v} value={v}>{label}<span className="ms-1.5 tabular-nums text-muted-foreground">{data ? data.counts[v] ?? 0 : ""}</span></TabsTrigger>)}
            </TabsList>
          </Tabs>
          <nav aria-label="Other job lists" className="flex flex-wrap items-center gap-x-3 text-sm text-muted-foreground">
            <span>Also:</span>
            {OTHER_VIEWS.map(([v, label]) => (
              <a key={v} href={href("jobs", null, { ...params, view: v })} aria-current={view === v ? "page" : undefined}
                className={cn("inline-flex min-h-11 items-center underline-offset-2 hover:underline", view === v ? "font-medium text-foreground" : "")}>
                {label} ({data?.counts[v] ?? 0})
              </a>))}
          </nav>
        </div>

        <div className="flex flex-wrap items-end gap-3" role="search" aria-label="Filter jobs">
          <div className="flex w-full flex-col gap-1 sm:w-72"><Label htmlFor="job-q">Search</Label>
            <Input id="job-q" type="search" placeholder="Title, employer or text" value={f.q} onChange={(e) => set("q", e.target.value)} /></div>
          <div className="flex w-full flex-col gap-1 sm:w-52"><Label htmlFor="job-loc">Location</Label>
            <NativeSelect id="job-loc" value={f.locgroup} onChange={(e) => set("locgroup", e.target.value)}>
              <option value="">Any</option>{data && Object.entries(data.groups).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </NativeSelect></div>
          <div className="flex w-full flex-col gap-1 sm:w-64"><Label htmlFor="job-family">Role family</Label>
            <NativeSelect id="job-family" value={f.family} onChange={(e) => set("family", e.target.value)}>
              <option value="">Any</option>{data && Object.entries(data.families).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </NativeSelect></div>
          <details className="group relative">
            <summary className="flex min-h-9 cursor-pointer list-none items-center rounded-md border border-border px-3 text-sm hover:bg-(--row-hover) [&::-webkit-details-marker]:hidden">
              More filters{moreActive ? ` (${moreActive})` : ""}
            </summary>
            <div className="z-20 mt-2 flex w-72 flex-col gap-3 rounded-lg border border-border bg-popover p-3 text-popover-foreground shadow-lg sm:absolute">
              <div className="flex flex-col gap-1"><Label htmlFor="job-status">Your status</Label>
                <NativeSelect id="job-status" value={f.status} onChange={(e) => set("status", e.target.value)}>
                  <option value="">Any active</option>{data?.statuses.map((s) => <option key={s}>{s}</option>)}
                </NativeSelect></div>
              <div className="flex flex-col gap-1"><Label htmlFor="job-comp">Pay against your target</Label>
                <NativeSelect id="job-comp" value={f.comp} onChange={(e) => set("comp", e.target.value)}>
                  <option value="">Any</option>{data && Object.entries(data.bands).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </NativeSelect></div>
              <div className="flex flex-col gap-1"><Label htmlFor="job-sort">Sort by</Label>
                <NativeSelect id="job-sort" value={f.sort || "first_seen"} onChange={(e) => set("sort", e.target.value === "first_seen" ? "" : e.target.value)}>
                  {Object.entries(SORTS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </NativeSelect></div>
            </div>
          </details>
        </div>

        <div className="flex flex-wrap items-center gap-2 text-sm" aria-live="polite">
          <span className="text-muted-foreground">
            {!data ? (error ?? "Loading") : activeChips.length || jobs.length !== total
              ? `Showing ${jobs.length} of ${total} ${VIEW_NOUN[view] ?? "jobs"}${jobs.length === 500 ? " (first 500)" : ""}`
              : `Showing all ${total} ${VIEW_NOUN[view] ?? "jobs"}`}
          </span>
          {activeChips.map((c) => (
            <button key={c.k} type="button" onClick={() => set(c.k, "")} className="inline-flex min-h-8 items-center gap-1 rounded-full bg-(--chip) px-3 text-(--chip-foreground) hover:bg-(--row-hover)"
              aria-label={`Remove filter ${c.text}`}>{c.text}<XIcon className="size-3.5" aria-hidden /></button>))}
          {activeChips.length > 1 && <button type="button" onClick={clearAll} className="min-h-8 px-2 text-(--primary-text) underline underline-offset-2">Clear all</button>}
        </div>
      </div>

      </div>
      <ListDetail hasSelection={!!route.id} backHref={link()} backLabel="Back to results"
        list={data && !jobs.length ? (
          <Empty title={activeChips.length ? "No jobs match these filters" : "No jobs here"}
            line={activeChips.length ? "Remove a filter above to see more." : view === "matches" ? "Nothing matches your role and location preferences yet. Run the Job Scout from Today, or look at To review." : "Nothing in this list yet."} />
        ) : (
          <ul ref={listRef} className="min-h-0 flex-1 overflow-y-auto" aria-label="Results">
            {jobs.map((j) => {
              const a = arrangement(j)
              const fullyNew = j.change_state === "new" && j.listing_state === "open"
              return (
                <ListItem key={j.id} selected={route.id === j.id} to={link(j.id)} onClick={remember}>
                  <span className="text-[0.95rem] font-semibold leading-snug">{j.title}</span>
                  <span className="text-sm text-muted-foreground">{j.employer}{!oneLocation || UNCERTAIN.has(j.location_class) ? ` · ${j.location_raw || "location not stated"}` : ""}</span>
                  <span className="flex flex-wrap gap-1.5 pt-1">
                    {view !== "outside" && view !== "closed" && <MatchPill match={j.match} pending={j.analysis_pending} />}
                    {!oneLocation && !UNCERTAIN.has(j.location_class) && <Pill tone={LOCATION_TONE[j.location_class] ?? "neutral"}>{data?.locationLabels[j.location_class] ?? j.location_class}</Pill>}
                    {UNCERTAIN.has(j.location_class) && <Pill tone="warning">Eligibility unclear</Pill>}
                    {a.hybrid && <Pill>Hybrid</Pill>}
                    {a.multiCity && <Pill>Several cities</Pill>}
                    {(j.comp_band === "above" || j.comp_band === "below") && <Pill tone={BAND_TONE[j.comp_band]} title={j.comp_note}>{data?.bands[j.comp_band]}</Pill>}
                    {j.verification_state === "unverified" && <Pill tone="warning">Not on employer's board yet</Pill>}
                    {j.change_state === "changed" && j.listing_state === "open" && <Pill>Changed</Pill>}
                    {fullyNew && !allNew && <Pill>New</Pill>}
                    {j.status !== "New" && <Pill tone={SHORTLISTED.includes(j.status) ? "success" : "neutral"}>{SHORTLISTED.includes(j.status) ? "Shortlisted" : j.status}</Pill>}
                  </span>
                  {(view === "review" || view === "outside") && <span className="text-xs text-muted-foreground">{j.bucket_reason.replace(/^Check: /, "")}</span>}
                </ListItem>
              )
            })}
          </ul>
        )}
        detail={route.id ? <JobView id={route.id} statuses={data?.statuses ?? []} onChange={reload} /> : <Empty title="Select a job" line="Its fit, what to check, and how to apply open here." />} />
      {allNew && jobs.length > 1 && <p className={cn("text-xs text-muted-foreground", route.id && "hidden lg:block")}>Every job shown is new since your last review{oneLocation ? `, all in ${data?.locationLabels[jobs[0].location_class]}` : ""}, so those labels are not repeated on each row.</p>}
      <ImportDialog open={importing} onOpenChange={setImporting} onDone={(id) => { reload(); go("jobs", id, params) }} />
    </div>
  )
}

// ------------------------------------------------------------------ detail
function JobView({ id, statuses, onChange }: { id: number; statuses: string[]; onChange: () => void }) {
  const { data: j, reload } = useApi<JobDetail>(`/api/jobs/${id}`)
  const [note, setNote] = useState<string | null>(null)
  useEffect(() => {
    if (!j?.task || !["queued", "running"].includes(j.task.status)) return
    const t = window.setInterval(reload, 4000)
    return () => window.clearInterval(t)
  }, [j?.task, reload])
  useEffect(() => setNote(null), [id])
  // On a phone the job replaces the list, so start at its top.
  useEffect(() => { if (window.matchMedia("(max-width: 1023px)").matches) document.getElementById("main")?.scrollTo({ top: 0 }) }, [id])
  if (!j) return <p className="p-6 text-sm text-muted-foreground" role="status">Loading</p>

  const setStatus = async (s: string) => { await api.send(`/api/jobs/${id}`, "PATCH", { status: s }); reload(); onChange() }
  const shortlisted = SHORTLISTED.includes(j.status)
  const toggleShortlist = () => setStatus(shortlisted ? "New" : "Interested")
  const analyse = async () => { const r = await api.send<{ result: string }>(`/api/jobs/${id}/analyse`, "POST"); setNote(r.result === "cached" ? "A saved analysis for this exact text and profile already exists." : "Queued for the local model."); reload() }
  const recheck = async () => { setNote("Checking the employer's board"); const r = await api.send<{ result: string }>(`/api/jobs/${id}/recheck`, "POST"); setNote(r.result); reload(); onChange() }

  const fit = j.fit && !j.fit.outdated ? j.fit.output : j.fit?.output
  // Show the fact text the model actually saw. Ids are renumbered when the profile
  // changes, so an outdated result without a snapshot can't be resolved safely.
  const sent = j.fit?.inputs.facts_sent
  const facts: Record<string, string> = Object.fromEntries((sent ?? (j.fit?.outdated ? [] : j.profile_facts)).map((x) => [x.id, x.text]))
  const waiting = j.task && ["queued", "running"].includes(j.task.status)
  const cov = j.fit?.inputs.coverage
  const partial = !!j.fit && ((cov && !cov.complete) || j.fit.validation.notes.some((n) => /partial/i.test(n)))
  const a = arrangement(j)
  const workRaw = j.workplace_raw || (a.hybrid ? "Hybrid" : a.remote ? "Remote" : a.onsite ? "On-site" : null)
  const work = workRaw && !(j.location_raw ?? "").toLowerCase().includes(workRaw.toLowerCase()) ? workRaw : null
  const unconfirmed = [
    ...(fit?.unknowns ?? []),
    ...((fit ? [...fit.essential, ...fit.preferred] : []).filter((r) => !r.quote_found).map((r) => `${r.req}: the quoted requirement was not found in the listing`)),
    ...(UNCERTAIN.has(j.location_class) ? [`Whether you can work from India: the listing says “${j.location_raw || "nothing about location"}”`] : []),
    ...(j.comp_band === "unknown" && !j.salary_text ? ["Pay: not disclosed"] : []),
  ]

  return (
    <article className="flex flex-col gap-6 p-5 text-[0.95rem] leading-relaxed" aria-labelledby="job-title">
      {/* First screenful: what it is, where, pay, and the two decisions. */}
      <header className="flex flex-col gap-3">
        <div className="flex flex-col gap-1">
          <h2 id="job-title" className="text-2xl font-semibold leading-tight tracking-tight">{j.title}</h2>
          <p className="text-muted-foreground">{j.employer} · {j.location_raw || "Location not stated"}{work ? ` · ${work}` : ""}</p>
          {j.salary_text && <p className="text-sm">{j.comp_note}</p>}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {j.apply_url && (
            <a href={j.apply_url} target="_blank" rel="noopener noreferrer"
              className="inline-flex min-h-11 items-center gap-2 rounded-lg bg-primary px-4 font-medium text-primary-foreground hover:bg-(--primary-hover) focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background">
              Apply on employer site<ArrowSquareOutIcon className="size-4" aria-hidden /><span className="sr-only">(opens in a new tab)</span>
            </a>)}
          <Button variant="outline" className="min-h-11" onClick={toggleShortlist} aria-pressed={shortlisted}>
            {shortlisted ? <><CheckCircleIcon className="size-4" />Shortlisted</> : <><BookmarkSimpleIcon className="size-4" />Shortlist</>}
          </Button>
          {j.official_url && j.official_url !== j.apply_url && <ExternalLink url={j.official_url} className="ms-1">Original listing</ExternalLink>}
        </div>
        <div className="flex flex-wrap gap-1.5">
          <MatchPill match={fit?.match} pending={!!waiting} />
          {partial && <Pill tone="warning" title="The model saw only part of the listing or your profile">Partial assessment</Pill>}
          {j.fit?.outdated && <Pill tone="warning">Assessment outdated</Pill>}
          {UNCERTAIN.has(j.location_class) && <Pill tone="warning">Eligibility unclear</Pill>}
          {j.listing_state === "open" ? <FreshnessPill hours={j.verified_hours_ago} /> : <Pill tone="danger">No longer listed since {day(j.closed_at)}</Pill>}
          {!!j.injection_flag && <Pill tone="warning" title="The text contains wording aimed at AI tools. It was treated as data and ignored.">Contains instructions aimed at AI</Pill>}
        </div>
      </header>

      {/* The decision: what supports it and what to verify before applying. */}
      {fit ? (
        <div className="grid gap-4 xl:grid-cols-2">
          <section aria-labelledby="why-fits" className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4 text-card-foreground">
            <h3 id="why-fits" className="font-semibold">Why it fits</h3>
            {fit.summary !== "unknown" && <p>{fit.summary}</p>}
            {fit.evidence.length ? (
              <ul className="flex flex-col gap-3">{fit.evidence.map((e) => (
                <li key={e.req} className="flex flex-col gap-1">
                  <span className="font-medium">{e.req}</span>
                  <span className="text-sm text-muted-foreground">Your background: {e.facts.map((x) => facts[x] ?? "a fact no longer in your profile").join(" · ")}</span>
                </li>))}</ul>
            ) : <p className="text-sm text-muted-foreground">No requirement was tied to a fact in your profile.</p>}
            {partial && <p className="text-sm text-(--warning-text)">Partial assessment: {cov && !cov.complete ? `the model read ${cov.chars_sent.toLocaleString("en-IN")} of ${cov.chars_total.toLocaleString("en-IN")} characters` : "only some of your profile facts were sent"}. Other strengths may be missing.</p>}
          </section>
          <section aria-labelledby="what-check" className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4 text-card-foreground">
            <h3 id="what-check" className="font-semibold">What to check</h3>
            {fit.gaps.length > 0 && (
              <div className="flex flex-col gap-1">
                <p className="text-sm font-medium">Gaps the model found</p>
                <ul className="flex list-disc flex-col gap-1 ps-5">{fit.gaps.map((g) => <li key={g}>{g}</li>)}</ul>
              </div>)}
            {unconfirmed.length > 0 && (
              <div className="flex flex-col gap-1">
                <p className="text-sm font-medium">Not established: confirm on the listing</p>
                <ul className="flex list-disc flex-col gap-1 ps-5">{unconfirmed.map((g) => <li key={g}>{g}</li>)}</ul>
              </div>)}
            {!fit.gaps.length && !unconfirmed.length && <p className="text-sm text-muted-foreground">Nothing flagged. Still check location and work authorisation on the listing.</p>}
          </section>
        </div>
      ) : (
        <section className="flex flex-col gap-2 rounded-xl border border-border bg-card p-4 text-card-foreground" aria-labelledby="not-assessed">
          <h3 id="not-assessed" className="font-semibold">{waiting ? "Assessment queued" : "Not assessed yet"}</h3>
          <p className="text-sm text-muted-foreground">{waiting ? `Waiting for the local model${j.task?.note ? `: ${j.task.note}` : ""}.` : "Ask the local model to compare this listing with your profile."}</p>
          {unconfirmed.length > 0 && <ul className="flex list-disc flex-col gap-1 ps-5 text-sm">{unconfirmed.map((g) => <li key={g}>{g}</li>)}</ul>}
        </section>
      )}

      {/* Everyday actions. */}
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex w-44 flex-col gap-1"><Label htmlFor="status">Your status</Label>
          <NativeSelect id="status" value={j.status} onChange={(e) => setStatus(e.target.value)}>{statuses.map((s) => <option key={s}>{s}</option>)}</NativeSelect></div>
        <Button variant="outline" onClick={analyse} disabled={!!waiting}>{j.fit ? (j.fit.outdated ? "Re-analyse (outdated)" : "Analyse again") : "Analyse fit"}</Button>
        <Button variant="ghost" onClick={recheck}><ArrowClockwiseIcon className="size-4" />Recheck listing</Button>
      </div>
      {note && <p role="status" className="text-sm text-muted-foreground">{note}</p>}
      {j.task?.status === "failed" && <p className="text-sm text-(--destructive-text)">The last analysis failed: {j.task.error}</p>}

      <ContactsSection job={j} onChange={reload} />
      <FundingSection f={j.funding} />

      {/* Everything else, one click away. */}
      <details className="rounded-xl border border-border">
        <summary className="flex min-h-11 cursor-pointer items-center px-4 font-medium">Assessment details and evidence trail</summary>
        <div className="flex flex-col gap-6 border-t border-border p-4">
          {j.fit ? (
            <>
              <ModelNote model={j.fit.model_id} at={j.fit.created_at} version={j.fit.prompt_version} notes={j.fit.validation.notes} coverage={j.fit.inputs.coverage} />
              {j.fit.outdated && <p className="text-sm text-(--warning-text)">Outdated: the text, your profile, the prompt or the model settings changed since. Run it again for a current result.</p>}
              <Requirements title="Essential requirements" items={j.fit.output.essential} />
              <Requirements title="Preferred" items={j.fit.output.preferred} />
              <p className="text-sm text-muted-foreground">A potential match is not confirmed eligibility: check location and work authorisation on the listing.</p>
            </>
          ) : <p className="text-sm text-muted-foreground">No model assessment yet.</p>}
          {!!j.role_evidence_list.length && (
            <Section title="Duties that place it in this role family">
              <ul className="flex flex-col gap-2">{j.role_evidence_list.map((e) => <li key={e}><Evidence quote={e} found /></li>)}</ul>
            </Section>
          )}
        </div>
      </details>
      <details className="rounded-xl border border-border">
        <summary className="flex min-h-11 cursor-pointer items-center px-4 font-medium">Listing details and source</summary>
        <div className="flex flex-col gap-4 border-t border-border p-4 text-sm">
          <Facts rows={[
            ["Pay as written", j.salary_text ?? "Not disclosed"],
            ["Pay type", j.salary_text ? j.salary_kind : null],
            ["Against your target", j.comp_note],
            ["Location as written", j.location_evidence || j.location_raw || "Not stated"],
            ["Workplace", j.workplace_raw],
            ["Role family", j.family_labels.join(" + ")],
            ["Why in this list", j.bucket_reason],
            ["Published", j.published_at ? day(j.published_at) : "Not stated by the source"],
            ["First seen", day(j.first_seen_at)],
            ["Last verified", j.last_verified_at ? when(j.last_verified_at) : j.verification_state === "unverified" ? "Not yet found on the employer's board" : "Never"],
            ["Found on", j.found_on.length ? j.found_on.map((s) => SOURCE_LABEL[s.source] ?? s.source).join(", ") : j.company ? `${j.source} board` : "Added by hand"],
            ["Changed", j.change_state === "changed" ? ago(j.changed_at) : null],
          ]} />
          {j.found_on.length > 1 && (
            <ul className="flex flex-col gap-1 text-xs">{j.found_on.map((s) => (
              <li key={s.source + s.url}><ExternalLink url={s.url}>{SOURCE_LABEL[s.source] ?? s.source}</ExternalLink> <span className="text-muted-foreground">first seen {day(s.first_seen_at)}</span></li>))}</ul>
          )}
          {j.company && <p className="text-xs text-muted-foreground">Board check: {j.company.verification}</p>}
          {!!j.duplicates.length && <p className="text-xs text-muted-foreground">{j.duplicates.length} duplicate listing(s) of this role are hidden.</p>}
          {!!j.versions.length && (
            <div><p className="font-medium">Earlier versions</p>
              <ul>{j.versions.map((v) => <li key={v.id}>{when(v.seen_at)}: {v.title} · {v.location_raw}{v.salary_text ? ` · ${v.salary_text}` : ""}</li>)}</ul></div>
          )}
          <div className="flex flex-col gap-2"><span className="font-medium">Use in briefings</span><FeedbackSelect type="job" id={j.id} value={j.feedback[0] ?? ""} onChange={() => reload()} /></div>
        </div>
      </details>
      <details className="rounded-xl border border-border">
        <summary className="flex min-h-11 cursor-pointer items-center px-4 font-medium">Full job description</summary>
        <div className="max-w-[72ch] whitespace-pre-wrap border-t border-border p-4 leading-relaxed">{j.description_text || "The board gave no description."}</div>
      </details>
    </article>
  )
}

function FundingSection({ f }: { f: JobDetail["funding"] }) {
  if (!f) return null
  const e = f.latest
  return (
    <Section title="Funding" aside={<a className="text-sm text-(--primary-text) underline underline-offset-2" href={href("funded", f.startup_id)}>Startup details</a>}>
      {e ? (
        <p className="text-sm">{e.investor ? `${e.investor} announced` : "Announced"} a {ROUND_LABEL(e.round).toLowerCase()} round{e.amount_text ? ` of ${e.amount_text}` : ""} on {day(e.announced_on)}
          {f.days_since !== null ? ` (${f.days_since} days ago)` : ""}. <ExternalLink url={e.announcement_url}>Announcement</ExternalLink></p>
      ) : <p className="text-sm text-muted-foreground">{f.name} is on your watchlist; no dated funding announcement has been found.</p>}
      <p className="text-xs text-muted-foreground">Shown for context. Funding recency never raises a job's match.</p>
    </Section>
  )
}

function ContactsSection({ job, onChange }: { job: JobDetail; onChange: () => void }) {
  const [note, setNote] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [adding, setAdding] = useState(false)
  const [form, setForm] = useState({ name: "", title: "", profile_url: "", evidence_url: "" })
  const find = async () => {
    setBusy(true); setNote(null)
    try {
      const r = await api.send<{ found: number; checked: string[] }>(`/api/jobs/${job.id}/contacts/discover`, "POST")
      setNote(r.found ? `${r.found} contact(s) found. Drafts are ready below; the local model may improve them.` : `No named person found in the ${r.checked.join(", ")}. You can add one yourself.`)
      onChange()
    } catch (e) { setNote(e instanceof Error ? e.message : String(e)) } finally { setBusy(false) }
  }
  const add = async (ev: React.FormEvent) => {
    ev.preventDefault()
    try {
      await api.send("/api/contacts", "POST", { ...form, job_id: job.id, company: job.employer })
      setForm({ name: "", title: "", profile_url: "", evidence_url: "" }); setAdding(false); onChange()
    } catch (e) { setNote(e instanceof Error ? e.message : String(e)) }
  }
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value })
  return (
    <Section title="Who to contact" aside={<div className="flex gap-2">
      <Button size="sm" variant="outline" onClick={find} disabled={busy}>{busy ? "Looking" : job.contacts.length ? "Look again" : "Find contacts"}</Button>
      <Button size="sm" variant="ghost" onClick={() => setAdding(!adding)} aria-expanded={adding}>Add one yourself</Button></div>}>
      {note && <p role="status" className="text-sm text-muted-foreground">{note}</p>}
      {adding && (
        <form onSubmit={add} className="grid gap-3 rounded-lg border border-border p-3 sm:grid-cols-2">
          <div className="flex flex-col gap-1"><Label htmlFor="c-name">Name</Label><Input id="c-name" required value={form.name} onChange={set("name")} /></div>
          <div className="flex flex-col gap-1"><Label htmlFor="c-title">Title</Label><Input id="c-title" value={form.title} onChange={set("title")} /></div>
          <div className="flex flex-col gap-1"><Label htmlFor="c-profile">Profile URL you opened</Label><Input id="c-profile" type="url" value={form.profile_url} onChange={set("profile_url")} /></div>
          <div className="flex flex-col gap-1"><Label htmlFor="c-evidence">Page that names them</Label><Input id="c-evidence" type="url" value={form.evidence_url} onChange={set("evidence_url")} /></div>
          <Button type="submit" className="w-fit">Save contact</Button>
        </form>
      )}
      {job.contacts.length ? <ul className="flex flex-col gap-3">{job.contacts.map((c) => <li key={c.id}><ContactCard c={c} onChange={onChange} /></li>)}</ul>
        : !adding && <p className="text-sm text-muted-foreground">None yet. People come from the posting and the company's own pages; nothing is sent for you.</p>}
    </Section>
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
            <DialogDescription>Paste the listing yourself. With only a link, SignalDesk reads it only from an employer job board or a careers site you track.</DialogDescription>
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
