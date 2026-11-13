import { useState } from "react"
import { Empty, PageHeader, Pill, RunHistoryLink, Section } from "@/components/common"
import { ContactCard } from "@/components/outreach"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { api, useApi, type Contact, type OutreachState } from "@/lib/api"
import { href } from "@/lib/router"

interface Item extends Contact {
  id: number; contact_id: number; job_id: number | null; job_title: string | null; apply_url: string | null; contact_title: string | null
  contact_status: Contact["status"]; updated_at: string; error: string | null
}
interface Resp {
  items: Item[]; counts: Record<string, number>
  settings: { autosend: boolean; daily_cap: number; stopped: boolean; job_ids: number[] }
  sending: { available: boolean; reason: string }
  unresolved: (Contact & { job_title: string | null })[]
}
const VIEWS: [string, string][] = [["drafted", "Ready to send"], ["contacted", "Contacted"], ["sent", "Sent"], ["problem", "Needs a look"]]

export default function Outreach() {
  const [view, setView] = useState("drafted")
  const state = view === "problem" ? "" : view
  const { data, reload } = useApi<Resp>(`/api/outreach?state=${state}`)
  const items = (data?.items ?? []).filter((i) => view !== "problem" || ["failed", "send_unknown", "sending"].includes(i.state as OutreachState))
  const problems = (data?.counts.failed ?? 0) + (data?.counts.send_unknown ?? 0) + (data?.counts.sending ?? 0)
  return (
    <div className="flex flex-col gap-8 p-4 sm:p-6">
      <PageHeader title="Outreach" line="People to contact about shortlisted roles. A draft is never a sent message."
        action={<RunHistoryLink agent="contact_scout" label="Contact Scout" />} />
      <Tabs value={view} onValueChange={(v) => setView(String(v))}>
        <TabsList className="flex-wrap">{VIEWS.map(([v, label]) => <TabsTrigger key={v} value={v}>{label} ({v === "problem" ? problems : data?.counts[v] ?? 0})</TabsTrigger>)}</TabsList>
      </Tabs>
      {data && !items.length ? (
        <Empty title={view === "drafted" ? "No drafts waiting" : "Nothing here"}
          line={view === "drafted" ? "Mark a job Interested, or open one and choose Find contacts. Drafts appear here." : "Items move here as you mark them."} />
      ) : (
        <ul className="grid max-w-5xl gap-4 lg:grid-cols-2">{items.map((i) => (
          <li key={i.id} className="flex flex-col gap-1.5">
            <p className="text-sm">For <a className="font-medium underline-offset-2 hover:underline" href={href("jobs", i.job_id)}>{i.job_title}</a> at {i.company}</p>
            {i.error && <p className="text-xs text-(--destructive-text)">{i.error}</p>}
            <ContactCard c={{ ...i, id: i.contact_id, title: i.contact_title, status: i.contact_status, outreach_id: i.id }} onChange={reload} />
          </li>))}</ul>
      )}
      {!!data?.unresolved.length && (
        <Section title="Not verified yet">
          <p className="text-sm text-muted-foreground">These people were named without a page that ties them to the company. They get no draft until you add that page.</p>
          <ul className="flex flex-col gap-1 text-sm">{data.unresolved.map((c) => <li key={c.id}>{c.name}{c.title ? `, ${c.title}` : ""} · {c.company}{c.job_title ? ` (${c.job_title})` : ""}</li>)}</ul>
        </Section>
      )}
      {data && <SendingSettings data={data} onSaved={reload} />}
    </div>
  )
}

function SendingSettings({ data, onSaved }: { data: Resp; onSaved: () => void }) {
  const s = data.settings
  const [cap, setCap] = useState(String(s.daily_cap))
  const [error, setError] = useState<string | null>(null)
  const save = async (change: Record<string, unknown>) => {
    try { await api.send("/api/outreach/settings", "PUT", change); setError(null); onSaved() } catch (e) { setError(e instanceof Error ? e.message : String(e)) }
  }
  return (
    <details className="max-w-3xl rounded-lg border border-border p-4">
      <summary className="cursor-pointer text-sm font-medium">Automatic sending: {data.sending.available ? (s.autosend && !s.stopped ? "on" : "off") : "not available"}</summary>
      <div className="mt-3 flex flex-col gap-3 text-sm">
        {!data.sending.available && <p>{data.sending.reason} Discovery and drafting still run on every sweep; send drafts yourself with Copy, then Mark contacted.</p>}
        <label className="flex items-center gap-2"><Switch checked={s.autosend} disabled={!data.sending.available} onCheckedChange={(v) => save({ autosend: !!v })} />Send drafts for the roles I select</label>
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex w-40 flex-col gap-1"><Label htmlFor="cap">Daily cap</Label>
            <Input id="cap" type="number" min={0} max={25} value={cap} onChange={(e) => setCap(e.target.value)} onBlur={() => save({ daily_cap: Number(cap) })} /></div>
          <Button variant="outline" onClick={() => save({ stopped: !s.stopped })}>{s.stopped ? "Resume sending" : "Stop all sending"}</Button>
        </div>
        <p className="text-muted-foreground">Each person is contacted once across roles. A send with an unclear result is held for you to check and is never retried automatically.</p>
        {s.stopped && <Pill tone="warning">Stopped</Pill>}
        {error && <p role="alert" className="text-(--destructive-text)">{error}</p>}
      </div>
    </details>
  )
}

