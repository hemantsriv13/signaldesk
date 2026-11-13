import { DiscoverySources } from "@/components/discovery-sources"
import { SourceDiscovery } from "@/components/source-discovery"
import { useState } from "react"
import { ExternalLink, PageHeader, Pill, Section } from "@/components/common"
import { PencilSimpleIcon, PlusIcon } from "@/components/icons"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { NativeSelect } from "@/components/ui/native-select"
import { Switch } from "@/components/ui/switch"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Textarea } from "@/components/ui/textarea"
import { api, useApi } from "@/lib/api"
import { ago } from "@/lib/format"

interface Company { id: number; name: string; careers_url: string; ats: string; ats_id: string | null; enabled: number; verification: string | null; last_success_at: string | null; last_error: string | null; last_warning: string | null; open_jobs: number; matches: number }
interface Feed { id: number; name: string; site_url: string | null; feed_url: string; kind: string; enabled: number; verification: string | null; last_success_at: string | null; last_error: string | null; items: number }

function Health({ ok, error, warning, enabled }: { ok: string | null; error: string | null; warning?: string | null; enabled: boolean }) {
  if (!enabled) return <span className="text-muted-foreground">Off</span>
  if (error) return <span className="text-(--destructive-text)">Failed: {error}</span>
  if (warning) return <span className="text-(--warning-text)">{warning}</span>
  if (!ok) return <span className="text-muted-foreground">Not checked yet</span>
  return <span>Checked {ago(ok)}</span>
}

export default function Sources() {
  const { data, reload } = useApi<{ companies: Company[]; feeds: Feed[] }>("/api/sources")
  const [editCo, setEditCo] = useState<Partial<Company> | null>(null)
  const [editFeed, setEditFeed] = useState<Partial<Feed> | null>(null)
  const [results, setResults] = useState<Record<string, string>>({})

  const test = async (kind: "companies" | "feeds", id: number) => {
    setResults((r) => ({ ...r, [`${kind}${id}`]: "Checking" }))
    const r = await api.send<{ result: string }>(`/api/sources/${kind}/${id}/test`, "POST")
    setResults((x) => ({ ...x, [`${kind}${id}`]: r.result }))
    reload()
  }
  const toggleCo = async (c: Company) => { await api.send(`/api/sources/companies/${c.id}`, "PUT", { ...c, ats_id: c.ats_id ?? "", verification: c.verification ?? "", enabled: !c.enabled }); reload() }
  const toggleFeed = async (f: Feed) => { await api.send(`/api/sources/feeds/${f.id}`, "PUT", { ...f, site_url: f.site_url ?? "", enabled: !f.enabled }); reload() }

  return (
    <div className="flex flex-col gap-8 p-4 sm:p-6">
      <PageHeader title="Sources" line="Employer job boards and reading feeds. Turning one off keeps what it already collected." />
      <SourceDiscovery onChoose={(board, url) => setEditCo({ name: "", ats: board.ats, ats_id: board.ats_id, careers_url: url, enabled: 0, verification: "Discovered from careers page; employer identity needs review" })} />
      <DiscoverySources />
      <Section title={`Employers (${data?.companies.filter((c) => c.enabled).length ?? 0} on)`}
        aside={<Button size="sm" variant="outline" onClick={() => setEditCo({ ats: "greenhouse", enabled: 1 })}><PlusIcon className="size-4" />Add employer</Button>}>
        <p className="max-w-[80ch] text-sm text-muted-foreground">Jobs come from each employer's public Greenhouse, Lever or Ashby board. Employers marked "manual" are not fetched: check their careers page yourself and add jobs by hand. LinkedIn is not scraped.</p>
        <Table>
          <TableHeader><TableRow><TableHead className="w-16">On</TableHead><TableHead>Employer</TableHead><TableHead>Board</TableHead><TableHead className="text-right">Open / matching</TableHead><TableHead>Last check</TableHead><TableHead><span className="sr-only">Actions</span></TableHead></TableRow></TableHeader>
          <TableBody>{data?.companies.map((c) => (
            <TableRow key={c.id}>
              <TableCell><Switch checked={!!c.enabled} onCheckedChange={() => toggleCo(c)} aria-label={`Fetch ${c.name}`} /></TableCell>
              <TableCell className="max-w-[18rem]"><span className="font-medium">{c.name}</span>
                <p className="text-xs text-muted-foreground">{c.verification}</p></TableCell>
              <TableCell>{c.ats === "manual" ? <Pill>Manual</Pill> : <span className="text-sm">{c.ats}: {c.ats_id}</span>}</TableCell>
              <TableCell className="text-right tabular-nums">{c.open_jobs} / {c.matches}</TableCell>
              <TableCell className="max-w-[18rem] text-sm"><Health ok={c.last_success_at} error={c.last_error} warning={c.last_warning} enabled={!!c.enabled} />
                {results[`companies${c.id}`] && <p className="text-xs text-muted-foreground" role="status">{results[`companies${c.id}`]}</p>}</TableCell>
              <TableCell>
                <div className="flex flex-wrap items-center justify-end gap-2">
                  <ExternalLink url={c.careers_url}>Careers page</ExternalLink>
                  {c.ats !== "manual" && <Button size="sm" variant="ghost" onClick={() => test("companies", c.id)}>Check now</Button>}
                  <Button size="icon-sm" variant="ghost" aria-label={`Edit ${c.name}`} onClick={() => setEditCo(c)}><PencilSimpleIcon className="size-4" /></Button>
                </div>
              </TableCell>
            </TableRow>))}</TableBody>
        </Table>
      </Section>

      <Section title={`Reading feeds (${data?.feeds.filter((f) => f.enabled).length ?? 0} on)`}
        aside={<Button size="sm" variant="outline" onClick={() => setEditFeed({ kind: "substack", enabled: 1 })}><PlusIcon className="size-4" />Add feed</Button>}>
        <p className="max-w-[80ch] text-sm text-muted-foreground">RSS and Atom feeds only. Paid posts usually arrive as previews and are labelled as excerpts; SignalDesk does not get around paywalls.</p>
        <Table>
          <TableHeader><TableRow><TableHead className="w-16">On</TableHead><TableHead>Feed</TableHead><TableHead>Type</TableHead><TableHead className="text-right">Items</TableHead><TableHead>Last check</TableHead><TableHead><span className="sr-only">Actions</span></TableHead></TableRow></TableHeader>
          <TableBody>{data?.feeds.map((f) => (
            <TableRow key={f.id}>
              <TableCell><Switch checked={!!f.enabled} onCheckedChange={() => toggleFeed(f)} aria-label={`Read ${f.name}`} /></TableCell>
              <TableCell className="max-w-[20rem]"><span className="font-medium">{f.name}</span><p className="text-xs text-muted-foreground">{f.verification}</p></TableCell>
              <TableCell>{f.kind === "vendor" ? <Pill tone="warning">Vendor</Pill> : <span className="text-sm">{f.kind}</span>}</TableCell>
              <TableCell className="text-right tabular-nums">{f.items}</TableCell>
              <TableCell className="max-w-[18rem] text-sm"><Health ok={f.last_success_at} error={f.last_error} enabled={!!f.enabled} />
                {results[`feeds${f.id}`] && <p className="text-xs text-muted-foreground" role="status">{results[`feeds${f.id}`]}</p>}</TableCell>
              <TableCell>
                <div className="flex flex-wrap items-center justify-end gap-2">
                  {f.site_url && <ExternalLink url={f.site_url}>Site</ExternalLink>}
                  <Button size="sm" variant="ghost" onClick={() => test("feeds", f.id)}>Check now</Button>
                  <Button size="icon-sm" variant="ghost" aria-label={`Edit ${f.name}`} onClick={() => setEditFeed(f)}><PencilSimpleIcon className="size-4" /></Button>
                </div>
              </TableCell>
            </TableRow>))}</TableBody>
        </Table>
      </Section>
      <CompanyDialog value={editCo} onClose={() => setEditCo(null)} onSaved={reload} />
      <FeedDialog value={editFeed} onClose={() => setEditFeed(null)} onSaved={reload} />
    </div>
  )
}

function CompanyDialog({ value, onClose, onSaved }: { value: Partial<Company> | null; onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState<Partial<Company>>({})
  const [error, setError] = useState<string | null>(null)
  const [seen, setSeen] = useState<Partial<Company> | null>(null)
  if (value !== seen) { setSeen(value); setForm(value ?? {}); setError(null) }
  const save = async (e: React.FormEvent) => {
    e.preventDefault()
    const body = { name: form.name ?? "", careers_url: form.careers_url ?? "", ats: form.ats ?? "greenhouse", ats_id: form.ats_id ?? "", enabled: !!form.enabled, verification: form.verification ?? "" }
    try {
      await (value?.id ? api.send(`/api/sources/companies/${value.id}`, "PUT", body) : api.send("/api/sources/companies", "POST", body))
      onSaved(); onClose()
    } catch (err) { setError(err instanceof Error ? err.message : String(err)) }
  }
  const set = (k: keyof Company) => (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value })
  return (
    <Dialog open={!!value} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-lg">
        <form onSubmit={save} className="flex flex-col gap-4">
          <DialogHeader><DialogTitle>{value?.id ? `Edit ${value.name}` : "Add an employer"}</DialogTitle>
            <DialogDescription>Use the employer's own careers page, and check that it links to the job board you enter.</DialogDescription></DialogHeader>
          <div className="flex flex-col gap-1"><Label htmlFor="co-name">Employer</Label><Input id="co-name" required value={form.name ?? ""} onChange={set("name")} /></div>
          <div className="flex flex-col gap-1"><Label htmlFor="co-url">Official careers URL</Label><Input id="co-url" required type="url" value={form.careers_url ?? ""} onChange={set("careers_url")} /></div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="flex flex-col gap-1"><Label htmlFor="co-ats">Job board</Label>
              <NativeSelect id="co-ats" value={form.ats ?? "greenhouse"} onChange={set("ats")}><option value="greenhouse">Greenhouse</option><option value="lever">Lever</option><option value="ashby">Ashby</option><option value="manual">Manual (not fetched)</option></NativeSelect></div>
            <div className="flex flex-col gap-1"><Label htmlFor="co-id">Board id</Label><Input id="co-id" value={form.ats_id ?? ""} onChange={set("ats_id")} disabled={form.ats === "manual"} placeholder="e.g. stripe" /></div>
          </div>
          <div className="flex flex-col gap-1"><Label htmlFor="co-ver">How you verified it</Label><Textarea id="co-ver" rows={2} value={form.verification ?? ""} onChange={set("verification")} /></div>
          {error && <p role="alert" className="text-sm text-(--destructive-text)">{error}</p>}
          <DialogFooter><Button type="submit">Save employer</Button></DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function FeedDialog({ value, onClose, onSaved }: { value: Partial<Feed> | null; onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState<Partial<Feed>>({})
  const [error, setError] = useState<string | null>(null)
  const [seen, setSeen] = useState<Partial<Feed> | null>(null)
  if (value !== seen) { setSeen(value); setForm(value ?? {}); setError(null) }
  const save = async (e: React.FormEvent) => {
    e.preventDefault()
    const body = { name: form.name ?? "", feed_url: form.feed_url ?? "", site_url: form.site_url ?? "", kind: form.kind ?? "blog", enabled: !!form.enabled }
    try {
      await (value?.id ? api.send(`/api/sources/feeds/${value.id}`, "PUT", body) : api.send("/api/sources/feeds", "POST", body))
      onSaved(); onClose()
    } catch (err) { setError(err instanceof Error ? err.message : String(err)) }
  }
  const set = (k: keyof Feed) => (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value })
  return (
    <Dialog open={!!value} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-lg">
        <form onSubmit={save} className="flex flex-col gap-4">
          <DialogHeader><DialogTitle>{value?.id ? `Edit ${value.name}` : "Add a feed"}</DialogTitle>
            <DialogDescription>Substack feeds end in /feed. Mark company blogs that promote their own products as Vendor.</DialogDescription></DialogHeader>
          <div className="flex flex-col gap-1"><Label htmlFor="f-name">Name</Label><Input id="f-name" required value={form.name ?? ""} onChange={set("name")} /></div>
          <div className="flex flex-col gap-1"><Label htmlFor="f-url">Feed URL</Label><Input id="f-url" required type="url" value={form.feed_url ?? ""} onChange={set("feed_url")} /></div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="flex flex-col gap-1"><Label htmlFor="f-site">Site URL</Label><Input id="f-site" type="url" value={form.site_url ?? ""} onChange={set("site_url")} /></div>
            <div className="flex flex-col gap-1"><Label htmlFor="f-kind">Type</Label>
              <NativeSelect id="f-kind" value={form.kind ?? "blog"} onChange={set("kind")}><option value="substack">Substack</option><option value="blog">Personal blog</option><option value="engineering">Engineering blog</option><option value="vendor">Vendor</option></NativeSelect></div>
          </div>
          {error && <p role="alert" className="text-sm text-(--destructive-text)">{error}</p>}
          <DialogFooter><Button type="submit">Save feed</Button></DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
