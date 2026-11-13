import { useEffect, useState } from "react"
import { useStatus } from "@/App"
import {
  BasisPill, Empty, Evidence, ExternalLink, Facts, FeedbackSelect, ListDetail, ListItem, ModelNote, PageHeader, Pill, RunHistoryLink, Section,
} from "@/components/common"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { NativeSelect } from "@/components/ui/native-select"
import { api, useApi, type Analysis, type ArticleRow, type Card, type CaseStudy, type TaskRef } from "@/lib/api"
import { day, when } from "@/lib/format"
import { href, useRoute } from "@/lib/router"

export interface ArticleDetail extends ArticleRow {
  content_text: string; duplicates: { id: number; title: string; url: string; source_name: string }[]
  card: Analysis<Card> | null; case: Analysis<CaseStudy> | null; card_task: TaskRef | null; case_task: TaskRef | null; feedback: string[]
}

export default function Reading() {
  const route = useRoute()
  const [q, setQ] = useState("")
  const [source, setSource] = useState("")
  const [basis, setBasis] = useState("")
  const [analysed, setAnalysed] = useState("")
  const { data, error, reload } = useApi<{ articles: ArticleRow[]; sources: { id: number; name: string }[] }>(
    `/api/articles?${new URLSearchParams(Object.entries({ q, source, basis, analysed }).filter(([, v]) => v))}`)
  const { status } = useStatus()
  useEffect(() => { reload() }, [status?.counts.cards, status?.counts.articles]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-8 p-4 sm:p-6">
      <PageHeader title="Reading" line="Posts from the newsletters and engineering blogs in Sources, summarised from what each feed actually provides."
        action={<RunHistoryLink agent="reading_scout" label="Reading Scout" />} />
      <div className="flex flex-wrap items-end gap-3" role="search">
        <div className="flex w-full flex-col gap-1 sm:w-64"><Label htmlFor="r-q">Search</Label><Input id="r-q" type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Title, source or text" /></div>
        <div className="flex w-52 flex-col gap-1"><Label htmlFor="r-src">Source</Label>
          <NativeSelect id="r-src" value={source} onChange={(e) => setSource(e.target.value)}><option value="">All sources</option>{data?.sources.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</NativeSelect></div>
        <div className="flex w-40 flex-col gap-1"><Label htmlFor="r-basis">Text available</Label>
          <NativeSelect id="r-basis" value={basis} onChange={(e) => setBasis(e.target.value)}><option value="">Any</option><option value="full">Full text</option><option value="excerpt">Excerpt only</option><option value="metadata">Title only</option></NativeSelect></div>
        <div className="flex w-40 flex-col gap-1"><Label htmlFor="r-an">Reading card</Label>
          <NativeSelect id="r-an" value={analysed} onChange={(e) => setAnalysed(e.target.value)}><option value="">Any</option><option value="yes">Has a card</option></NativeSelect></div>
      </div>
      <ListDetail hasSelection={!!route.id} backHref={href("reading")}
        list={
          <>
            <p className="border-b border-border px-4 py-2 text-xs text-muted-foreground" aria-live="polite">{data ? `${data.articles.length} shown, newest first` : error ?? "Loading"}</p>
            {data && !data.articles.length ? <Empty title="No articles" line="Nothing collected matches. Run the Reading Scout from Today, or add feeds in Sources." /> : (
              <ul className="min-h-0 flex-1 overflow-y-auto">{data?.articles.map((a) => (
                <ListItem key={a.id} selected={route.id === a.id} to={href("reading", a.id)}>
                  <span className="font-medium leading-snug">{a.title}</span>
                  <span className="text-sm text-muted-foreground">{a.source_name} · {day(a.published_at ?? a.retrieved_at)}</span>
                  <span className="flex flex-wrap gap-1.5 pt-0.5">
                    <BasisPill basis={a.content_basis} />
                    {a.has_card ? <Pill tone="success">Card</Pill> : a.card_pending ? <Pill>Card queued</Pill> : null}
                    {!!a.repeats && <Pill>Also in {a.repeats} other place{a.repeats > 1 ? "s" : ""}</Pill>}
                    {a.feedback.map((f) => <Pill key={f}>{f.replace("_", " ")}</Pill>)}
                  </span>
                </ListItem>))}</ul>
            )}
          </>
        }
        detail={route.id ? <ArticleView id={route.id} onChange={reload} /> : <Empty title="Select an article" line="Its reading card, the evidence it rests on and a link to the original open here." />} />
    </div>
  )
}

export function ArticleView({ id, onChange, focus = "card" }: { id: number; onChange: () => void; focus?: "card" | "case" }) {
  const { data: a, reload } = useApi<ArticleDetail>(`/api/articles/${id}`)
  const [note, setNote] = useState<string | null>(null)
  const waiting = a && [a.card_task, a.case_task].some((t) => t && ["queued", "running"].includes(t.status))
  useEffect(() => {
    if (!waiting) return
    const t = window.setInterval(reload, 4000)
    return () => window.clearInterval(t)
  }, [waiting, reload])
  useEffect(() => setNote(null), [id])
  if (!a) return <p className="p-6 text-sm text-muted-foreground">Loading</p>

  const run = async (kind: "reading_card" | "case_study") => {
    try {
      const r = await api.send<{ result: string }>(`/api/articles/${id}/analyse?kind=${kind}`, "POST")
      setNote(r.result === "cached" ? "A saved result for this text already exists." : "Queued for the local model.")
    } catch (e) { setNote(e instanceof Error ? e.message : String(e)) }
    reload()
    onChange()
  }
  const card = a.card?.output
  return (
    <article className="flex flex-col gap-6 p-5" aria-labelledby="art-title">
      <header className="flex flex-col gap-2">
        <h2 id="art-title" className="font-heading text-2xl font-medium leading-tight">{a.title}</h2>
        <p className="text-sm text-muted-foreground">{a.source_name}{a.author ? ` · ${a.author}` : ""}</p>
        <div className="flex flex-wrap gap-1.5">
          <BasisPill basis={a.content_basis} />
          {a.source_kind === "vendor" && <Pill tone="warning">Vendor-published</Pill>}
          {!!a.injection_flag && <Pill tone="warning">Contains instructions aimed at AI</Pill>}
        </div>
        <ExternalLink url={a.url}>Read the original</ExternalLink>
      </header>
      {a.content_basis !== "full" && (
        <p className="max-w-[70ch] text-sm text-(--warning-text)">
          {a.content_basis === "excerpt" ? "Only an excerpt or preview was available, so anything below describes that excerpt, not the whole article." : "Only the title and link were available; there is nothing to summarise."}
        </p>
      )}
      <div className="grid grid-cols-1 gap-8 xl:grid-cols-[minmax(0,1fr)_16rem]">
        <div className="flex min-w-0 flex-col gap-6">
          {focus === "card" && (card ? (
            <>
              <Section title="Main argument"><p className="max-w-[70ch]">{card.main_argument}</p>
                <ModelNote model={a.card!.model_id} at={a.card!.created_at} version={a.card!.prompt_version} notes={a.card!.validation.notes} coverage={a.card!.inputs.coverage} /></Section>
              <Section title="Evidence presented">
                {card.evidence.length ? <ul className="flex flex-col gap-3">{card.evidence.map((e) => (
                  <li key={e.point} className="grid gap-2 md:grid-cols-2"><p>{e.point}</p><Evidence quote={e.quote} found={e.quote_found} /></li>))}</ul>
                  : <p className="text-sm text-muted-foreground">The model found no evidence presented.</p>}
              </Section>
              <Section title="Why it might matter to you"><p className="max-w-[70ch]">{card.why_it_matters}</p></Section>
              <Section title="Uncertainties and limits"><p className="max-w-[70ch]">{card.limitations}</p></Section>
              <Section title={`Concept: ${card.concept.term}`}><p className="max-w-[70ch]">{card.concept.explanation}</p></Section>
            </>
          ) : (
            <Section title="Reading card">
              <p className="text-sm text-muted-foreground">{a.card_task && ["queued", "running"].includes(a.card_task.status) ? "Waiting for the local model." : a.card_task?.status === "failed" ? `The last attempt failed: ${a.card_task.error}` : "Not analysed yet."}</p>
              {a.content_basis !== "metadata" && <Button variant="outline" className="w-fit" onClick={() => run("reading_card")}>Write a reading card</Button>}
            </Section>
          ))}
          {focus === "case" && <CaseView a={a} onRun={() => run("case_study")} />}
          {note && <p role="status" className="text-sm text-muted-foreground">{note}</p>}
          {a.content_basis !== "metadata" && (
            <Section title="Retrieved text">
              <div className="max-h-[28rem] max-w-[72ch] overflow-y-auto whitespace-pre-wrap rounded-lg border border-border p-4 text-[0.95rem] leading-relaxed" tabIndex={0} aria-label="Retrieved text">{a.content_text}</div>
            </Section>
          )}
        </div>
        <aside className="flex flex-col gap-5 text-sm" aria-label="Article facts">
          <Facts rows={[
            ["Published", a.published_at ? day(a.published_at) : "Not stated"],
            ["Retrieved", when(a.retrieved_at)],
            ["Source type", a.source_kind ?? "unknown"],
            ["Came from", a.origin === "manual" ? "A link you added" : "The source's feed"],
          ]} />
          {focus === "card" && a.content_basis === "full" && (
            <a className="text-(--primary-text) underline" href={href("cases", a.id)}>{a.case ? "Open its case study" : "Analyse as a case study"}</a>
          )}
          {!!a.duplicates.length && (
            <div><p className="font-medium">Same story elsewhere</p><ul className="text-xs text-muted-foreground">{a.duplicates.map((d) => <li key={d.id}>{d.source_name}: {d.title}</li>)}</ul>
              <p className="text-xs text-muted-foreground">Repeats are not independent confirmation.</p></div>
          )}
          <div className="flex flex-col gap-2"><span className="font-medium">Use in briefings</span><FeedbackSelect type="article" id={a.id} value={a.feedback[0] ?? ""} onChange={() => { reload(); onChange() }} /></div>
        </aside>
      </div>
    </article>
  )
}

const LABEL: Record<string, { text: string; tone: "success" | "warning" | "neutral" | "danger" }> = {
  source_fact: { text: "Source-reported", tone: "success" }, vendor_claim: { text: "Vendor claim", tone: "warning" },
  inference: { text: "Analyst's inference", tone: "neutral" }, missing: { text: "Missing evidence", tone: "danger" },
}
const FIELDS: [string, string][] = [
  ["problem_owner", "Who has the problem"], ["existing_workflow", "Existing workflow"], ["bottleneck", "Bottleneck"], ["ai_contribution", "Where AI contributes"],
  ["ordinary_software", "What ordinary software still does"], ["data_needed", "Data needed"], ["failure_modes", "Failure modes"], ["impact_evidence", "Evidence of impact"],
  ["lesson", "One lesson to apply"], ["experiment", "One small experiment"],
]

function CaseView({ a, onRun }: { a: ArticleDetail; onRun: () => void }) {
  const c = a.case?.output
  if (!c) {
    const t = a.case_task
    return (
      <Section title="Case study">
        <p className="text-sm text-muted-foreground">{t && ["queued", "running"].includes(t.status) ? "Waiting for the local model (two requests)." : t?.status === "failed" ? `The last attempt failed: ${t.error}` : "Not analysed as a case study yet."}</p>
        {a.content_basis === "full" ? <Button variant="outline" className="w-fit" onClick={onRun}>Analyse as a case study</Button>
          : <p className="text-sm text-muted-foreground">Case studies need the full text; this item has {a.content_basis === "excerpt" ? "an excerpt only" : "no text"}.</p>}
      </Section>
    )
  }
  return (
    <>
      <Section title="Case study">
        <div className="flex flex-wrap items-center gap-2">
          <Pill tone={c.suitability === "strong" ? "success" : "warning"}>{c.suitability === "strong" ? "Strong case study" : c.suitability === "weak" ? "Weak case study" : c.suitability === "none" ? "Not a case study" : "Suitability unknown"}</Pill>
          <span className="text-sm text-muted-foreground">{c.suitability_reason !== "unknown" ? c.suitability_reason : ""}</span>
        </div>
        <ModelNote model={a.case!.model_id} at={a.case!.created_at} version={a.case!.prompt_version} notes={a.case!.validation.notes} coverage={a.case!.inputs.coverage} />
        {a.case!.outdated && <p className="text-sm text-(--warning-text)">Outdated: the text, your profile, the prompt or the model settings changed since. Run it again for a current result.</p>}
      </Section>
      <dl className="flex flex-col divide-y divide-border">
        {FIELDS.map(([k, label]) => {
          const f = c[k]
          if (!f) return null
          return (
            <div key={k} className="grid gap-2 py-3 md:grid-cols-[12rem_minmax(0,1fr)_minmax(0,1fr)]">
              <dt className="font-medium">{label}</dt>
              <dd className="flex flex-col gap-1.5"><span>{f.text}</span><span><Pill tone={LABEL[f.label].tone}>{LABEL[f.label].text}</Pill></span></dd>
              <dd>{f.quote ? <Evidence quote={f.quote} found /> : <span className="text-xs text-muted-foreground">{f.label === "inference" ? "Reasoning, not a quote" : "No passage"}</span>}</dd>
            </div>
          )
        })}
      </dl>
    </>
  )
}
