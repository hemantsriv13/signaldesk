import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { api } from "@/lib/api"

export interface DiscoveredBoard { ats: string; ats_id: string; url: string }
export function SourceDiscovery({ onChoose }: { onChoose: (b: DiscoveredBoard, url: string) => void }) {
  const [url, setUrl] = useState("")
  const [query, setQuery] = useState("AI product manager")
  const [boards, setBoards] = useState<DiscoveredBoard[]>([])
  const [message, setMessage] = useState("")
  const [busy, setBusy] = useState(false)
  const discover = async () => {
    setBusy(true); setBoards([]); setMessage("")
    try {
      const r = await api.send<{ boards: DiscoveredBoard[]; note: string }>("/api/sources/discover", "POST", { url })
      setBoards(r.boards); setMessage(r.note)
    } catch (e) { setMessage(e instanceof Error ? e.message : String(e)) }
    finally { setBusy(false) }
  }
  return <section className="discovery-card grid gap-5 rounded-2xl border p-5 sm:grid-cols-2">
    <div className="flex flex-col gap-3"><p className="text-xs font-semibold uppercase tracking-widest text-primary">Grow your opportunity radar</p><h2 className="font-heading text-2xl">Follow the companies you care about.</h2><p className="text-sm text-muted-foreground">Paste a careers page to find its public job board. You confirm the employer before adding it.</p>
      <Label htmlFor="career-discovery">Company careers URL</Label><Input id="career-discovery" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://company.com/careers" type="url" />
      <Button className="w-fit" disabled={busy || !url.trim()} onClick={discover}>{busy ? "Looking for boards…" : "Find job board"}</Button>
      {message && <p role="status" className="text-sm">{message}</p>}
      {boards.map((b) => <div key={b.ats + b.ats_id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border bg-card p-3 text-sm"><span>{b.ats}: {b.ats_id}</span><Button variant="outline" onClick={() => onChoose(b, url)}>Review employer</Button></div>)}
    </div>
    <div className="flex flex-col gap-3 rounded-xl bg-background/70 p-4"><h3 className="font-semibold">Search wider, apply at the source</h3><p className="text-sm text-muted-foreground">Find employers on LinkedIn, then paste their careers page here.</p>
      <Label htmlFor="discovery-keywords">Role keywords</Label><Input id="discovery-keywords" value={query} onChange={(e) => setQuery(e.target.value)} />
      <a className="flex min-h-11 items-center text-sm font-medium text-primary underline" href={`https://www.linkedin.com/jobs/search/?keywords=${encodeURIComponent(query)}&location=Bengaluru%2C%20Karnataka%2C%20India`} target="_blank" rel="noreferrer">Search Bengaluru jobs on LinkedIn ↗</a>
      <a className="flex min-h-11 items-center text-sm font-medium text-primary underline" href={`https://www.linkedin.com/jobs/search/?keywords=${encodeURIComponent(query)}&location=India&f_WT=2`} target="_blank" rel="noreferrer">Search remote jobs in India ↗</a>
      
    </div>
  </section>
}
