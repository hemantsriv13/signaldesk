import { useEffect, useState } from "react"
import { useStatus } from "@/App"
import { BasisPill, Empty, ListDetail, ListItem, PageHeader, Pill, RunHistoryLink } from "@/components/common"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { api, useApi, type ArticleRow } from "@/lib/api"
import { day } from "@/lib/format"
import { go, href, useRoute } from "@/lib/router"
import { ArticleView } from "@/pages/Reading"

export default function Cases() {
  const route = useRoute()
  const [q, setQ] = useState("")
  const { data, error, reload } = useApi<{ articles: ArticleRow[] }>(`/api/cases?${new URLSearchParams({ q })}`)
  const { status } = useStatus()
  useEffect(() => { reload() }, [status?.counts.cases, status?.queue.queued]) // eslint-disable-line react-hooks/exhaustive-deps
  const [url, setUrl] = useState("")
  const [msg, setMsg] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const add = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setMsg(null)
    try {
      const r = await api.send<{ id: number; analysis: string }>("/api/cases/import", "POST", { url })
      setMsg(r.analysis === "queued" ? "Saved and queued for analysis." : r.analysis === "cached" ? "Already analysed." : r.analysis)
      setUrl("")
      reload()
      go("cases", r.id)
    } catch (err) { setMsg(err instanceof Error ? err.message : String(err)) } finally { setBusy(false) }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-8 p-4 sm:p-6">
      <PageHeader title="Case studies" line="Real uses of AI, taken apart: the problem, the workflow, what AI does and what the evidence actually shows."
        action={<RunHistoryLink agent="case_analyst" label="Case Study Analyst" />} />
      <div className="flex flex-col gap-4">
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex w-full flex-col gap-1 sm:w-64"><Label htmlFor="c-q">Search</Label><Input id="c-q" type="search" value={q} onChange={(e) => setQ(e.target.value)} /></div>
          <form onSubmit={add} className="flex w-full flex-wrap items-end gap-2 sm:w-auto">
            <div className="flex w-full flex-col gap-1 sm:w-96"><Label htmlFor="c-url">Analyse a public article</Label>
              <Input id="c-url" type="url" required placeholder="https://" value={url} onChange={(e) => setUrl(e.target.value)} /></div>
            <Button type="submit" variant="outline" disabled={busy}>{busy ? "Fetching" : "Add and analyse"}</Button>
          </form>
        </div>
        {msg && <p role="status" className="text-sm text-muted-foreground">{msg}</p>}
      </div>
      <ListDetail hasSelection={!!route.id} backHref={href("cases")}
        list={
          <>
            <p className="border-b border-border px-4 py-2 text-xs text-muted-foreground" aria-live="polite">{data ? `${data.articles.length} candidates and analyses` : error ?? "Loading"}</p>
            {data && !data.articles.length ? <Empty title="No case studies yet" line="Articles that describe a real deployment are picked up after the Reading Scout runs. You can also paste a public link above." /> : (
              <ul className="min-h-0 flex-1 overflow-y-auto">{data?.articles.map((a) => (
                <ListItem key={a.id} selected={route.id === a.id} to={href("cases", a.id)}>
                  <span className="font-medium leading-snug">{a.title}</span>
                  <span className="text-sm text-muted-foreground">{a.source_name} · {day(a.published_at ?? a.retrieved_at)}</span>
                  <span className="flex flex-wrap gap-1.5 pt-0.5">
                    {a.case_suitability ? <Pill tone={a.case_suitability === "strong" ? "success" : "warning"}>{a.case_suitability === "strong" ? "Strong" : a.case_suitability === "weak" ? "Weak" : a.case_suitability === "none" ? "Not a case study" : "Unknown"}</Pill>
                      : a.case_pending ? <Pill>Queued</Pill> : <Pill>Candidate</Pill>}
                    <BasisPill basis={a.content_basis} />
                    {a.source_kind === "vendor" && <Pill tone="warning">Vendor</Pill>}
                  </span>
                </ListItem>))}</ul>
            )}
          </>
        }
        detail={route.id ? <ArticleView id={route.id} onChange={reload} focus="case" /> : <Empty title="Select a case study" line="Each claim is labelled as source-reported, vendor claim, inference or missing, with the passage it rests on." />} />
    </div>
  )
}
