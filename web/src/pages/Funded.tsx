import { useState } from "react"
import { Empty, ExternalLink, Facts, ListDetail, ListItem, PageHeader, Pill, RunHistoryLink, Section } from "@/components/common"
import { ContactCard } from "@/components/outreach"
import { PlusIcon } from "@/components/icons"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { NativeSelect } from "@/components/ui/native-select"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { api, useApi, type Contact, type FundingEvent, type Tone } from "@/lib/api"
import { day, ROUND_LABEL, when } from "@/lib/format"
import { go, href, useRoute } from "@/lib/router"

interface StartupRow {
  id: number; name: string; domain: string | null; india_link: string; india_evidence: string | null; careers_status: string; careers_url: string | null
  watch_source: string | null; latest: FundingEvent | null; rounds: number; openings: { open: number; matching: number; review: number }; opening_state: string
}
interface StartupDetail extends Omit<StartupRow, "latest" | "rounds" | "openings"> {
  events: FundingEvent[]; careers_label: string; careers_note: string | null; careers_checked_at: string | null; india_evidence_url: string | null
  domain_evidence: string | null; watch_url: string | null
  openings: { open: number; matching: number; review: number; jobs: { id: number; title: string; location_raw: string | null; bucket: string }[] }
  contacts: Contact[]
}
const WINDOWS: [string, string][] = [["30", "Last 30 days"], ["90", "Last 90 days"], ["180", "Last 180 days"], ["watch", "Watchlist, no dated round"]]
const INDIA: Record<string, [string, Tone]> = {
  india_based: ["India-based", "success"], hiring_in_india: ["Overseas, hiring in India", "neutral"], unknown: ["India link not confirmed", "warning"],
}

function openingTone(s: StartupRow | StartupDetail): Tone {
  if (s.careers_status !== "board_found") return "warning"
  return s.openings.matching ? "success" : "neutral"
}

export default function Funded() {
  const route = useRoute()
  const win = route.params.get("window") ?? "180"
  const [india, setIndia] = useState("all")
  const [adding, setAdding] = useState(false)
  const { data, error, reload } = useApi<{ startups: StartupRow[]; counts: Record<string, number> }>(`/api/funding?window=${win}&india=${india}`)
  const link = (id?: number) => href("funded", id, { window: win })
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-8 p-4 sm:p-6">
      <PageHeader title="Funded startups" line="Startups with a dated funding round, and whether they are hiring for your roles."
        action={<><RunHistoryLink agent="funding_scout" label="Funding Scout" /><Button variant="outline" onClick={() => setAdding(true)}><PlusIcon className="size-4" />Add a startup</Button></>} />
      <div className="flex flex-col gap-4">
        <Tabs value={win} onValueChange={(v) => go("funded", null, { window: String(v) })}>
          <TabsList className="flex-wrap">{WINDOWS.map(([v, label]) => <TabsTrigger key={v} value={v}>{label}{data ? ` (${data.counts[v] ?? 0})` : ""}</TabsTrigger>)}</TabsList>
        </Tabs>
        <div className="flex w-64 flex-col gap-1"><Label htmlFor="india">India connection</Label>
          <NativeSelect id="india" value={india} onChange={(e) => setIndia(e.target.value)}>
            <option value="all">Any</option><option value="based">India-based</option><option value="hiring">Overseas, hiring in India</option><option value="linked">Either, confirmed</option>
          </NativeSelect></div>
      </div>
      <ListDetail hasSelection={!!route.id} backHref={link()}
        list={
          <>
            <p className="border-b border-border px-4 py-2 text-xs text-muted-foreground" aria-live="polite">{data ? `${data.startups.length} shown` : error ?? "Loading"}</p>
            {data && !data.startups.length ? (
              <Empty title={win === "watch" ? "Watchlist is empty" : "No dated rounds in this window"}
                line={win === "watch" ? "Portfolio companies without a dated funding announcement. Being in a portfolio is not treated as funding." : "Add or set up announcement sources in Sources, then run the Funding Scout."} />
            ) : (
              <ul className="min-h-0 flex-1 overflow-y-auto">{data?.startups.map((s) => (
                <ListItem key={s.id} selected={route.id === s.id} to={link(s.id)}>
                  <span className="font-medium leading-snug">{s.name}</span>
                  <span className="text-sm text-muted-foreground">
                    {s.latest ? `${s.latest.investor ?? "Investor not named"} · ${ROUND_LABEL(s.latest.round)} · ${day(s.latest.announced_on)}` : `Listed by ${s.watch_source ?? "a portfolio page"}`}
                  </span>
                  <span className="flex flex-wrap gap-1.5 pt-0.5">
                    <Pill tone={openingTone(s)}>{s.opening_state}</Pill>
                    <Pill tone={INDIA[s.india_link]?.[1] ?? "neutral"}>{INDIA[s.india_link]?.[0] ?? s.india_link}</Pill>
                  </span>
                </ListItem>))}</ul>
            )}
          </>
        }
        detail={route.id ? <StartupView id={route.id} onChange={reload} /> : <Empty title="Select a startup" line="Its funding evidence, careers page and openings open here." />} />
      <AddStartup open={adding} onOpenChange={setAdding} onDone={(id) => { reload(); go("funded", id, { window: win }) }} />
    </div>
  )
}

function StartupView({ id, onChange }: { id: number; onChange: () => void }) {
  const { data: s, reload } = useApi<StartupDetail>(`/api/funding/${id}`)
  const [note, setNote] = useState<string | null>(null)
  if (!s) return <p className="p-6 text-sm text-muted-foreground">Loading</p>
  const recheck = async () => {
    setNote("Checking the company's careers page")
    const r = await api.send<{ boards: number; page_only: number; failed: number }>(`/api/funding/${id}/resolve`, "POST")
    setNote(r.boards ? "Job board found and added. Its openings arrive with the next job sweep." : r.page_only ? "A careers page was found, but SignalDesk can't read it." : "No careers page could be reached.")
    reload(); onChange()
  }
  return (
    <article className="flex flex-col gap-6 p-5" aria-labelledby="startup-title">
      <header className="flex flex-col gap-2">
        <h2 id="startup-title" className="font-heading text-2xl font-medium leading-tight">{s.name}</h2>
        <div className="flex flex-wrap gap-1.5">
          <Pill tone={openingTone(s)}>{s.opening_state}</Pill>
          <Pill tone={INDIA[s.india_link]?.[1] ?? "neutral"}>{INDIA[s.india_link]?.[0] ?? s.india_link}</Pill>
        </div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          {s.domain && <ExternalLink url={`https://${s.domain}`}>{s.domain}</ExternalLink>}
          {s.careers_url && <ExternalLink url={s.careers_url}>Careers page</ExternalLink>}
          <Button size="sm" variant="ghost" onClick={recheck} disabled={!s.domain}>Check careers page again</Button>
        </div>
        {note && <p role="status" className="text-sm text-muted-foreground">{note}</p>}
      </header>

      <Section title="Funding">
        {s.events.length ? (
          <ul className="flex flex-col gap-3">{s.events.map((e) => (
            <li key={e.id} className="flex flex-col gap-1">
              <p><span className="font-medium">{ROUND_LABEL(e.round)}</span>{e.amount_text ? `, ${e.amount_text}` : ""} · {e.investor ?? "investor not named"} · announced {day(e.announced_on)}</p>
              <ExternalLink url={e.announcement_url}>{e.title || "Announcement"}</ExternalLink>
              {!!e.other_reports?.length && <p className="text-xs text-muted-foreground">Also reported by {e.other_reports.length} other source(s); counted once.</p>}
            </li>))}</ul>
        ) : <p className="text-sm text-muted-foreground">No dated funding announcement. {s.watch_source ? `Listed on ${s.watch_source}, which does not say when it was funded.` : ""}</p>}
      </Section>

      <Section title="Openings">
        <p className="text-sm">{s.careers_label}{s.careers_checked_at ? ` (checked ${when(s.careers_checked_at)})` : ""}.</p>
        {s.careers_note && <p className="text-sm text-(--warning-text)">{s.careers_note}</p>}
        {s.openings.jobs.length ? (
          <ul className="flex flex-col gap-1 text-sm">{s.openings.jobs.map((j) => (
            <li key={j.id}><a className="underline-offset-2 hover:underline" href={href("jobs", j.id)}>{j.title}</a>
              <span className="text-muted-foreground"> · {j.location_raw ?? "location not stated"}{j.bucket === "review" ? " · to review" : ""}</span></li>))}</ul>
        ) : s.careers_status === "board_found" && <p className="text-sm text-muted-foreground">{s.openings.open ? `${s.openings.open} open role(s), none in your role families and locations.` : "No open roles right now."}</p>}
      </Section>

      <Section title="Evidence">
        <Facts rows={[
          ["India connection", s.india_evidence ?? "Not confirmed by any page yet"],
          ["India evidence page", s.india_evidence_url ? <ExternalLink url={s.india_evidence_url}>Source</ExternalLink> : null],
          ["Website from", s.domain_evidence],
          ["Watchlist source", s.watch_url ? <ExternalLink url={s.watch_url}>{s.watch_source ?? "Portfolio page"}</ExternalLink> : null],
        ]} />
      </Section>

      {!!s.contacts.length && (
        <Section title="People named on public pages">
          <ul className="flex flex-col gap-3">{s.contacts.map((c) => <li key={c.id}><ContactCard c={c} onChange={reload} /></li>)}</ul>
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
            <DialogDescription>Without a round it goes to the watchlist. A round needs its announcement date and link.</DialogDescription>
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
