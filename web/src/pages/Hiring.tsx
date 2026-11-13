import { useState } from "react"
import { useStatus } from "@/App"
import { Empty, ExternalLink, ListDetail, ListItem, PageHeader, Pill, RunHistoryLink, Section } from "@/components/common"
import { ArrowClockwiseIcon, ArrowSquareOutIcon, PlusIcon, WarningIcon, XIcon } from "@/components/icons"
import { ContactCard } from "@/components/outreach"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { NativeSelect } from "@/components/ui/native-select"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { api, useApi, type Contact, type FundingEvent } from "@/lib/api"
import { ago, day, ROUND_LABEL, when } from "@/lib/format"
import { go, href, useRoute } from "@/lib/router"
import { cn } from "@/lib/utils"

interface Board { state: string; careers_url: string | null; last_success_at: string | null; last_attempt_at: string | null; error: string | null; warning: string | null }
interface CompanyRow {
  key: string; name: string; company_id: number | null; openings: number; openings_all_families: number; other_open: number; closed: number
  state: "hiring" | "filtered" | "no_eligible" | "unchecked"; preview: string[]; families: string[]; matches: number; shortlisted: number
  investors: string[]; latest_round: FundingEvent | null; board: Board; last_verified_at: string | null
}
interface SourceState { key: string; name: string; mode: string; modeLabel: string; error: string | null; last_success_at: string | null }
interface RunState { status: string; started_at: string; finished_at: string | null }
interface HiringList {
  companies: CompanyRow[]; investors: string[]; families: Record<string, string>
  counts: { hiring: number; openings: number; all: number; hiring_unfiltered: number; openings_unfiltered: number }
  refresh: { running: boolean; funding_scout: RunState | null; job_scout: RunState | null; sources: SourceState[] }
}
interface Opening {
  id: number; title: string; location_raw: string | null; location_label: string; families: string[]; status: string; bucket: string
  match: string | null; verification_state: string; last_verified_at: string | null; apply_url: string | null; official_url: string | null
}
interface CompanyDetail {
  key: string; name: string; company_id: number | null; board: Board; openings: Opening[]; other_open: number; closed: number
  startup_id: number | null; investors: string[]; portfolio: string | null
}
interface StartupDetail {
  events: (FundingEvent & { other_reports?: unknown[] })[]; watch_source: string | null; watch_url: string | null; domain: string | null
  india_evidence: string | null; contacts: Contact[]
}

const BOARD_PROBLEM: Record<string, string> = {
  failed: "Job board could not be checked", unreadable: "Careers page can't be read automatically", no_website: "Company website not known yet",
  unchecked: "Not checked yet", no_careers_page: "No careers page found",
}
const SHORTLIST = ["Interested", "Investigate", "Applied"]

export default function Hiring() {
  const route = useRoute()
  const p = route.params
  const view = p.get("view") === "all" ? "all" : "hiring"
  const fams = (p.get("fam") ?? "").split(",").filter(Boolean)
  const backing = p.get("backing") ?? "all"
  const [q, setQ] = useState(p.get("q") ?? "")
  // Old links (#/funded/<startup id>) still open the right company.
  const selected = p.get("co") ?? (route.id ? `s${route.id}` : null)
  const params = (over: Record<string, string | null> = {}) => {
    const base: Record<string, string | null> = { view: view === "all" ? "all" : null, fam: fams.join(",") || null, backing: backing === "all" ? null : backing, q: q || null, ...over }
    return Object.fromEntries(Object.entries(base).filter(([, v]) => v)) as Record<string, string>
  }
  const nav = (over: Record<string, string | null>) => go("hiring", null, params(over))
  const query = new URLSearchParams({ view, families: fams.join(","), backing, q }).toString()
  const { data, error, reload } = useApi<HiringList>(`/api/hiring?${query}`)
  const { status } = useStatus()
  const [refreshNote, setRefreshNote] = useState<string | null>(null)
  const [adding, setAdding] = useState(false)

  const toggleFamily = (f: string) => nav({ fam: (fams.includes(f) ? fams.filter((x) => x !== f) : [...fams, f]).join(",") || null, co: null })
  const refresh = async () => {
    setRefreshNote(null)
    try {
      const r = await api.send<{ started: number[]; skipped?: string }>("/api/sweep", "POST", { scope: "hiring" })
      setRefreshNote(r.skipped ?? "Refreshing: discovering portfolio companies, then rechecking every employer's job board. Saved openings stay visible meanwhile.")
      reload()
    } catch (e) { setRefreshNote(e instanceof Error ? e.message : String(e)) }
  }
  const running = data?.refresh.running || !!status?.runs.some((r) => r.agent === "funding_scout" || r.agent === "job_scout")
  const lastRun = data?.refresh.job_scout
  const filtersOn = fams.length > 0 || backing !== "all" || !!q
  const c = data?.counts
  const failing = data?.refresh.sources.filter((s) => s.mode === "unavailable") ?? []
  const setup = data?.refresh.sources.filter((s) => s.mode === "needs_setup") ?? []

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-5 p-4 sm:p-6">
      <div className={cn("flex flex-col gap-5", selected && "hidden lg:flex")}>
        <PageHeader sans title="Hiring companies" line="Employers with open roles in Bengaluru or remote from India, from the same listings as Jobs."
          action={<>
            <RunHistoryLink agent="funding_scout" label="Funding Scout" />
            <Button variant="outline" onClick={() => setAdding(true)}><PlusIcon className="size-4" />Add a startup</Button>
            <Button onClick={refresh} disabled={running}><ArrowClockwiseIcon className={cn("size-4", running && "animate-spin motion-reduce:animate-none")} />{running ? "Refreshing" : "Refresh hiring"}</Button>
          </>} />
        <p className="text-sm text-muted-foreground" aria-live="polite">
          {refreshNote ?? (lastRun?.finished_at ? `Job boards last checked ${ago(lastRun.finished_at)}${lastRun.status === "done_with_errors" ? ", with some sources failing" : ""}.` : "Job boards have not been checked yet.")}
        </p>

        <div className="flex flex-col gap-3">
          <Tabs value={view} onValueChange={(v) => nav({ view: v === "all" ? "all" : null, co: null })}>
            <TabsList aria-label="Company lists">
              <TabsTrigger value="hiring">Hiring now<span className="ms-1.5 tabular-nums text-muted-foreground">{c ? c.hiring : ""}</span></TabsTrigger>
              <TabsTrigger value="all">All companies<span className="ms-1.5 tabular-nums text-muted-foreground">{c ? c.all : ""}</span></TabsTrigger>
            </TabsList>
          </Tabs>

          <div className="flex flex-wrap items-end gap-3" role="search" aria-label="Filter companies">
            <form className="flex w-full flex-col gap-1 sm:w-72" onSubmit={(e) => { e.preventDefault(); nav({ q: q || null, co: null }) }}>
              <Label htmlFor="h-q">Search</Label>
              <Input id="h-q" type="search" placeholder="Company or role title" value={q} onChange={(e) => setQ(e.target.value)} onBlur={() => nav({ q: q || null })} />
            </form>
            <div className="flex w-full flex-col gap-1 sm:w-64"><Label htmlFor="h-backing">Backing</Label>
              <NativeSelect id="h-backing" value={backing} onChange={(e) => nav({ backing: e.target.value === "all" ? null : e.target.value, co: null })}>
                <option value="all">All companies</option>
                <option value="backed">Investor or portfolio evidence</option>
                {data?.investors.map((i) => <option key={i} value={`investor:${i}`}>{i}</option>)}
                <option value="unknown">Backing not known</option>
              </NativeSelect></div>
          </div>

          <fieldset className="flex flex-col gap-1.5">
            <legend className="mb-1.5 text-sm font-medium">Role families</legend>
            <div className="flex flex-wrap gap-2">
              <button type="button" aria-pressed={!fams.length} onClick={() => nav({ fam: null, co: null })}
                className={cn("inline-flex min-h-9 items-center rounded-full border px-3 text-sm", !fams.length ? "border-(--row-indicator) bg-(--row-selected) text-(--row-selected-foreground) font-medium" : "border-border hover:bg-(--row-hover)")}>All roles</button>
              {data && Object.entries(data.families).map(([k, label]) => {
                const on = fams.includes(k)
                return (
                  <button key={k} type="button" aria-pressed={on} onClick={() => toggleFamily(k)}
                    className={cn("inline-flex min-h-9 items-center rounded-full border px-3 text-sm", on ? "border-(--row-indicator) bg-(--row-selected) text-(--row-selected-foreground) font-medium" : "border-border hover:bg-(--row-hover)")}>{label}</button>)
              })}
            </div>
          </fieldset>

          <div className="flex flex-wrap items-center gap-2 text-sm" aria-live="polite">
            <span className="text-muted-foreground">
              {!data ? (error ?? "Loading") : view === "hiring"
                ? (filtersOn ? `Showing ${c!.hiring} of ${c!.hiring_unfiltered} hiring companies · ${c!.openings} of ${c!.openings_unfiltered} eligible openings`
                  : `${c!.hiring} companies with ${c!.openings} eligible openings`)
                : `Showing ${data.companies.length} companies`}
            </span>
            {filtersOn && <button type="button" onClick={() => { setQ(""); nav({ fam: null, backing: null, q: null, co: null }) }}
              className="inline-flex min-h-8 items-center gap-1 rounded-full bg-(--chip) px-3 text-(--chip-foreground) hover:bg-(--row-hover)">Clear filters<XIcon className="size-3.5" aria-hidden /></button>}
          </div>
        </div>
      </div>

      <ListDetail hasSelection={!!selected} backHref={href("hiring", null, params({ co: null }))} backLabel="Back to companies"
        list={data && !data.companies.length ? (
          <EmptyState data={data} filtersOn={filtersOn} view={view} failing={failing} setup={setup} onClear={() => { setQ(""); nav({ fam: null, backing: null, q: null }) }} onRefresh={refresh} running={running} />
        ) : (
          <ul className="min-h-0 flex-1 overflow-y-auto" aria-label="Companies">
            {data?.companies.map((co) => (
              <ListItem key={co.key} selected={selected === co.key} to={href("hiring", null, params({ co: co.key }))}>
                <span className="flex items-baseline justify-between gap-3">
                  <span className="text-[0.95rem] font-semibold leading-snug">{co.name}</span>
                  <span className="shrink-0 text-sm tabular-nums">{co.openings ? `${co.openings} opening${co.openings === 1 ? "" : "s"}` : ""}</span>
                </span>
                {co.preview.length > 0 && <span className="text-sm text-muted-foreground">{co.preview.join(" · ")}{co.openings > co.preview.length ? ` and ${co.openings - co.preview.length} more` : ""}</span>}
                <span className="flex flex-wrap gap-1.5 pt-1">
                  {co.state === "no_eligible" && <Pill>{co.other_open || co.closed ? "No eligible openings" : "No open roles"}</Pill>}
                  {co.state === "filtered" && <Pill>{co.openings_all_families} opening(s) in other role families</Pill>}
                  {(co.state === "unchecked" || co.board.state === "failed") && <Pill tone="warning">{BOARD_PROBLEM[co.board.state] ?? "Could not be checked"}</Pill>}
                  {co.matches > 0 && <Pill tone="success">{co.matches} in your target roles</Pill>}
                  {co.shortlisted > 0 && <Pill tone="success">{co.shortlisted} shortlisted</Pill>}
                  {co.investors.map((i) => <Pill key={i}>{i}</Pill>)}
                </span>
              </ListItem>))}
          </ul>
        )}
        detail={selected ? <CompanyView key={selected} id={selected} onChange={reload} /> : <Empty title="Select a company" line="Its eligible openings, with Apply links, and what is known about its backing open here." />} />
      <AddStartup open={adding} onOpenChange={setAdding} onDone={(id) => { reload(); nav({ co: `s${id}`, view: "all" }) }} />
    </div>
  )
}

function EmptyState({ data, filtersOn, view, failing, setup, onClear, onRefresh, running }: {
  data: HiringList; filtersOn: boolean; view: string; failing: SourceState[]; setup: SourceState[]; onClear: () => void; onRefresh: () => void; running: boolean
}) {
  if (filtersOn && (data.counts.hiring_unfiltered > 0 || view === "all")) {
    return (
      <div className="flex flex-col items-start gap-3 p-5">
        <h2 className="font-semibold">Filters hide every company</h2>
        <p className="text-sm text-muted-foreground">{data.counts.hiring_unfiltered} companies have {data.counts.openings_unfiltered} eligible openings without these filters.</p>
        <Button variant="outline" onClick={onClear}>Clear filters</Button>
      </div>
    )
  }
  return (
    <div className="flex flex-col items-start gap-3 p-5">
      <h2 className="font-semibold">No eligible openings yet</h2>
      <p className="text-sm text-muted-foreground">No saved listing is open in Bengaluru or remote from India.</p>
      {failing.length > 0 && <ul className="flex flex-col gap-1 text-sm">{failing.map((s) => <li key={s.key} className="flex gap-1.5"><WarningIcon className="mt-0.5 size-4 shrink-0 text-(--warning-text)" aria-hidden /><span><span className="font-medium">{s.name} could not be checked:</span> {s.error}</span></li>)}</ul>}
      {setup.length > 0 && <p className="text-sm text-muted-foreground">Not set up yet: {setup.map((s) => s.name).join(", ")}. Add their page addresses in Sources.</p>}
      <Button onClick={onRefresh} disabled={running}>{running ? "Refreshing" : "Refresh hiring"}</Button>
    </div>
  )
}

function CompanyView({ id, onChange }: { id: string; onChange: () => void }) {
  const { data: c, error, reload } = useApi<CompanyDetail>(`/api/hiring/company?key=${encodeURIComponent(id)}`)
  const { data: s, reload: reloadStartup } = useApi<StartupDetail>(c?.startup_id ? `/api/funding/${c.startup_id}` : null)
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null)
  const [busy, setBusy] = useState(false)
  if (error) return <p className="p-6 text-sm" role="alert">{error}</p>
  if (!c) return <p className="p-6 text-sm text-muted-foreground" role="status">Loading</p>
  const recheck = async () => {
    setBusy(true); setNote(null)
    try {
      const r = await api.send<{ ok: boolean; error: string | null; counts: Record<string, number> }>(`/api/hiring/company/refresh?key=${encodeURIComponent(c.key)}`, "POST")
      setNote(r.ok ? { ok: true, text: `Checked just now${r.counts.fetched !== undefined ? `: ${r.counts.fetched} roles on the board, ${r.counts.new ?? 0} new, ${r.counts.closed ?? 0} closed` : ""}.` }
        : { ok: false, text: "The check failed; saved openings were kept." })
    } catch (e) { setNote({ ok: false, text: `${e instanceof Error ? e.message : String(e)} Saved openings were kept.` }) }
    finally { setBusy(false); reload(); reloadStartup(); onChange() }
  }
  const b = c.board
  const verified = b.last_success_at ? `Last verified ${when(b.last_success_at)}` : "Not verified on the employer's board yet"
  return (
    <article className="flex flex-col gap-6 p-5 text-[0.95rem] leading-relaxed" aria-labelledby="company-title">
      <header className="flex flex-col gap-2">
        <h2 id="company-title" className="text-2xl font-semibold leading-tight tracking-tight">{c.name}</h2>
        <p className="text-muted-foreground">{c.openings.length} eligible opening{c.openings.length === 1 ? "" : "s"}{c.other_open ? ` · ${c.other_open} more open elsewhere` : ""}{c.closed ? ` · ${c.closed} closed` : ""}</p>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
          <span>{verified}</span>
          {b.careers_url && <ExternalLink url={b.careers_url}>Careers page</ExternalLink>}
          {(c.company_id || c.startup_id) && <Button size="sm" variant="outline" onClick={recheck} disabled={busy}><ArrowClockwiseIcon className="size-4" />{busy ? "Checking" : "Check this company now"}</Button>}
        </div>
        {b.state === "failed" && <p className="flex gap-1.5 text-sm text-(--warning-text)"><WarningIcon className="mt-0.5 size-4 shrink-0" aria-hidden />
          <span>The last check failed{b.last_attempt_at ? ` (${when(b.last_attempt_at)})` : ""}: {b.error?.replace(/\.$/, "")}. {b.last_success_at ? "Openings shown are from the last successful check." : "It has never been checked successfully."}</span></p>}
        {b.state !== "failed" && b.state !== "ok" && b.state !== "listing_only" && <p className="text-sm text-(--warning-text)">{BOARD_PROBLEM[b.state]}{b.error ? `: ${b.error}` : "."}</p>}
        {b.state === "listing_only" && <p className="text-sm text-muted-foreground">These listings came from a listing site; the employer's own board is not tracked yet.</p>}
        {note && <p role="status" className={cn("text-sm", note.ok ? "text-muted-foreground" : "text-(--warning-text)")}>{note.text}</p>}
      </header>

      <Section title="Openings">
        {c.openings.length ? (
          <ul className="flex flex-col divide-y divide-border rounded-xl border border-border">{c.openings.map((o) => (
            <li key={o.id} className="flex flex-col gap-2 p-4 sm:flex-row sm:items-start sm:justify-between">
              <div className="flex min-w-0 flex-col gap-1">
                <a className="font-semibold underline-offset-2 hover:underline" href={href("jobs", o.id)}>{o.title}</a>
                <span className="text-sm text-muted-foreground">{o.location_raw || o.location_label} · {o.families.join(" + ")}</span>
                <span className="text-xs text-muted-foreground">{o.verification_state === "unverified" ? "Not yet on the employer's board" : o.last_verified_at ? `Verified ${ago(o.last_verified_at)}` : "Not verified yet"}</span>
                <span className="flex flex-wrap gap-1.5">
                  {o.match && <Pill tone={o.match === "potential match" ? "success" : o.match === "not a match" ? "danger" : "neutral"}>Model: {o.match}</Pill>}
                  {o.bucket === "candidate" && !o.match && <Pill tone="success">In your target roles</Pill>}
                  {SHORTLIST.includes(o.status) ? <Pill tone="success">{o.status === "Applied" ? "Applied" : "Shortlisted"}</Pill> : o.status !== "New" && <Pill>{o.status}</Pill>}
                </span>
              </div>
              {o.apply_url && (
                <a href={o.apply_url} target="_blank" rel="noopener noreferrer"
                  className="inline-flex min-h-10 shrink-0 items-center gap-2 rounded-lg bg-primary px-3 text-sm font-medium text-primary-foreground hover:bg-(--primary-hover) focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background">
                  Apply<ArrowSquareOutIcon className="size-4" aria-hidden /><span className="sr-only"> to {o.title} on the employer's site (opens in a new tab)</span>
                </a>)}
            </li>))}</ul>
        ) : (
          <p className="text-sm text-muted-foreground">
            {b.state === "failed" || (b.state !== "ok" && b.state !== "listing_only") ? "Openings could not be checked, so none are known."
              : c.other_open || c.closed ? `No eligible openings. ${[c.other_open && `${c.other_open} open ${c.other_open === 1 ? "role is" : "roles are"} outside Bengaluru and remote-from-India`, c.closed && `${c.closed} ${c.closed === 1 ? "role is" : "roles are"} closed`].filter(Boolean).join("; ")}.` : "No open roles right now."}
          </p>
        )}
      </Section>

      <Section title="Backing">
        {c.investors.length ? <p className="text-sm">Evidence of backing: {c.investors.join(", ")}.</p> : <p className="text-sm text-muted-foreground">Backing not known. Companies are listed whether or not their investors are known.</p>}
        {s?.events.length ? (
          <ul className="flex flex-col gap-2 text-sm">{s.events.map((e) => (
            <li key={e.id}><span className="font-medium">{ROUND_LABEL(e.round)}</span>{e.amount_text ? `, ${e.amount_text}` : ""} · {e.investor ?? "investor not named"} · announced {day(e.announced_on)}{" "}
              <ExternalLink url={e.announcement_url}>Announcement</ExternalLink></li>))}</ul>
        ) : c.startup_id && <p className="text-sm text-muted-foreground">No dated funding announcement{s?.watch_source ? `. Listed in a portfolio, which does not say when it was funded` : ""}.{" "}
          {s?.watch_url && <ExternalLink url={s.watch_url}>Portfolio page</ExternalLink>}</p>}
      </Section>

      {!!s?.contacts.length && (
        <Section title="People named on public pages">
          <ul className="flex flex-col gap-3">{s.contacts.map((x) => <li key={x.id}><ContactCard c={x} onChange={reloadStartup} /></li>)}</ul>
        </Section>
      )}
    </article>
  )
}

function AddStartup({ open, onOpenChange, onDone }: { open: boolean; onOpenChange: (o: boolean) => void; onDone: (id: number) => void }) {
  const blank = { name: "", domain: "", investor: "", round: "", amount: "", announced_on: "", announcement_url: "" }
  const [form, setForm] = useState(blank)
  const [error, setError] = useState<string | null>(null)
  const set = (k: keyof typeof blank) => (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value })
  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      const r = await api.send<{ id: number }>("/api/funding", "POST", form)
      onOpenChange(false); setForm(blank); setError(null); onDone(r.id)
    } catch (err) { setError(err instanceof Error ? err.message : String(err)) }
  }
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl">
        <form onSubmit={submit} className="flex flex-col gap-4">
          <DialogHeader>
            <DialogTitle>Add a startup</DialogTitle>
            <DialogDescription>With a website, its careers page is checked on the next refresh. A funding round needs its announcement date and link.</DialogDescription>
          </DialogHeader>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="flex flex-col gap-1"><Label htmlFor="s-name">Company (required)</Label><Input id="s-name" required value={form.name} onChange={set("name")} /></div>
            <div className="flex flex-col gap-1"><Label htmlFor="s-domain">Website</Label><Input id="s-domain" placeholder="example.com" value={form.domain} onChange={set("domain")} /></div>
            <div className="flex flex-col gap-1"><Label htmlFor="s-investor">Investor</Label><Input id="s-investor" value={form.investor} onChange={set("investor")} /></div>
            <div className="flex flex-col gap-1"><Label htmlFor="s-round">Round</Label><Input id="s-round" placeholder="Series A" value={form.round} onChange={set("round")} /></div>
            <div className="flex flex-col gap-1"><Label htmlFor="s-amount">Amount as written</Label><Input id="s-amount" value={form.amount} onChange={set("amount")} /></div>
            <div className="flex flex-col gap-1"><Label htmlFor="s-date">Announcement date</Label><Input id="s-date" type="date" value={form.announced_on} onChange={set("announced_on")} /></div>
          </div>
          <div className="flex flex-col gap-1"><Label htmlFor="s-url">Announcement link</Label><Input id="s-url" type="url" value={form.announcement_url} onChange={set("announcement_url")} /></div>
          {error && <p role="alert" className="text-sm text-(--destructive-text)">{error}</p>}
          <DialogFooter><Button type="submit">Add startup</Button></DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
