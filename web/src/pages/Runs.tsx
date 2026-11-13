import { useEffect } from "react"
import { useStatus } from "@/App"
import { Empty, Facts, ListDetail, ListItem, PageHeader, Pill, Section } from "@/components/common"
import { Button } from "@/components/ui/button"
import { NativeSelect } from "@/components/ui/native-select"
import { Label } from "@/components/ui/label"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { api, useApi, type Tone } from "@/lib/api"
import { AGENT_PAGE, when } from "@/lib/format"
import { go, href, useRoute } from "@/lib/router"

interface RunRow { id: number; agent: string; agentName: string; trigger: string; status: string; started_at: string; finished_at: string | null; stats: Record<string, number>; tasks: Record<string, number> }
interface RunDetail extends Omit<RunRow, "tasks"> {
  log: { at: string; msg: string }[]
  tasks: TaskRow[]
  calls: { purpose: string; model_served: string | null; duration_ms: number | null; tokens_in: number | null; tokens_out: number | null; finish_reason: string | null; ok: number; error: string | null; started_at: string }[]
}
interface Usage { week: Record<string, number | null>; all: Record<string, number | null>; modelsServed: { model_served: string; n: number }[]; paidApis: string; note: string }

const TASK_LABEL: Record<string, string> = { digest_compose: "Briefing", case_select: "Case selection", contact_select: "Contact search", "funding_extract": "Funding announcement", outreach_draft: "Outreach draft" }

const STATUS: Record<string, [string, Tone]> = {
  collecting: ["Collecting", "neutral"], analysing: ["Analysing", "neutral"], done: ["Done", "success"], done_with_errors: ["Done with errors", "warning"],
  failed: ["Failed", "danger"], cancelled: ["Cancelled", "neutral"],
}

export default function Runs() {
  const route = useRoute()
  const agent = route.params.get("agent") ?? ""
  const { data, reload } = useApi<{ runs: RunRow[]; agents: Record<string, string> }>(`/api/runs?agent=${agent}`)
  const { status } = useStatus()
  useEffect(() => { reload() }, [status?.runs.length, status?.queue.queued]) // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-8 p-4 sm:p-6">
      <PageHeader title="Agent runs" line="Every run, what it fetched, what it sent to the model and what failed." />
      <div className="flex flex-col gap-4">
        <UsageSummary />
        <div className="flex w-56 flex-col gap-1"><Label htmlFor="agent">Agent</Label>
          <NativeSelect id="agent" value={agent} onChange={(e) => go("runs", null, { agent: e.target.value })}>
            <option value="">All agents</option>{data && Object.entries(data.agents).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </NativeSelect></div>
      </div>
      <ListDetail hasSelection={!!route.id} backHref={href("runs", null, { agent })}
        list={data && !data.runs.length ? <Empty title="No runs yet" line="Start one with Run now on Today." /> : (
          <ul className="min-h-0 flex-1 overflow-y-auto">{data?.runs.map((r) => {
            const [label, tone] = STATUS[r.status] ?? [r.status, "neutral"]
            return (
              <ListItem key={r.id} selected={route.id === r.id} to={href("runs", r.id, { agent })}>
                <span className="flex items-baseline justify-between gap-2"><span className="font-medium">{r.agentName}</span><span className="text-xs text-muted-foreground">#{r.id}</span></span>
                <span className="text-sm text-muted-foreground">{when(r.started_at)} · {r.trigger}</span>
                <span className="flex flex-wrap gap-1.5"><Pill tone={tone}>{label}</Pill>{!!r.tasks.failed && <Pill tone="danger">{r.tasks.failed} failed</Pill>}</span>
              </ListItem>)
          })}</ul>
        )}
        detail={route.id ? <RunView id={route.id} onChange={reload} /> : <Empty title="Select a run" line="Its log, tasks and model requests open here." />} />
    </div>
  )
}

function UsageSummary() {
  const { data } = useApi<Usage>("/api/usage", 30000)
  if (!data) return null
  const w = data.week
  const tokens = w.tokensIn === null ? "not reported" : `${(w.tokensIn ?? 0).toLocaleString("en-IN")} in / ${(w.tokensOut ?? 0).toLocaleString("en-IN")} out`
  return (
    <section aria-label="Usage in the last 7 days" className="flex flex-col gap-2 border-y border-border py-3 text-sm">
      <p className="font-medium">Last 7 days</p>
      <p className="flex flex-wrap gap-x-6 gap-y-1 text-muted-foreground">
        <span>{w.fetched} items fetched</span><span>{w.analysed} analysed</span><span>{w.cacheHits} cache hits</span>
        <span>{w.modelRequests} model requests ({w.failedRequests} failed)</span><span>Tokens: {tokens}</span>
        <span>{w.modelSeconds} s of model time</span><span>{w.retries} retries, {w.errors} errors</span><span>Paid AI APIs: none; optional cloud costs are separate</span>
      </p>
      <p className="text-xs text-muted-foreground">{data.note}{w.requestsWithoutTokenCounts ? ` ${w.requestsWithoutTokenCounts} requests had no token counts from the server.` : ""}</p>
    </section>
  )
}

interface TaskRow { id: number; kind: string; target_type: string; target_id: number; target_title: string | null; status: string; attempts: number; max_attempts: number; error: string | null; note: string | null }

function RunView({ id, onChange }: { id: number; onChange: () => void }) {
  const { data, reload } = useApi<RunDetail>(`/api/runs/${id}`, 4000)
  if (!data) return <p className="p-6 text-sm text-muted-foreground">Loading</p>
  const s = data.stats
  const active = ["collecting", "analysing"].includes(data.status)
  const act = async (what: "cancel" | "retry") => { await api.send(`/api/runs/${id}/${what}`, "POST"); reload(); onChange() }
  const [label, tone] = STATUS[data.status] ?? [data.status, "neutral"]
  const link = (t: TaskRow) => t.target_type === "job" ? href("jobs", t.target_id) : t.target_type === "article" ? href(t.kind === "case_study" ? "cases" : "reading", t.target_id) : null
  return (
    <div className="flex flex-col gap-6 p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-col gap-1"><h2 className="font-heading text-2xl font-medium">{data.agentName} run #{data.id}</h2>
          <span className="flex items-center gap-2 text-sm text-muted-foreground"><Pill tone={tone}>{label}</Pill>{when(data.started_at)}{data.finished_at ? ` to ${when(data.finished_at)}` : ""}</span></div>
        <div className="flex gap-2">
          {active && <Button variant="outline" onClick={() => act("cancel")}>Cancel run</Button>}
          {!!data.tasks.filter((t) => t.status === "failed").length && <Button variant="outline" onClick={() => act("retry")}>Retry failed tasks</Button>}
          <a className="self-center text-sm text-(--primary-text) underline" href={href(AGENT_PAGE[data.agent])}>Results</a>
        </div>
      </div>
      <Facts rows={[
        ["Sources checked", s.sources_ok !== undefined ? `${s.sources_ok} ok, ${s.sources_failed ?? 0} with problems` : null],
        ["Fetched", s.fetched !== undefined ? `${s.fetched} items (${s.new ?? 0} new${s.changed !== undefined ? `, ${s.changed} changed` : ""}${s.closed !== undefined ? `, ${s.closed} no longer listed` : ""})` : null],
        ["Analysed", `${s.analysed ?? 0}, plus ${s.cache_hits ?? 0} reused from cache`],
        ["Model requests", `${s.model_requests ?? 0}${s.model_ms ? `, ${(s.model_ms / 1000).toFixed(1)} s` : ""}`],
        ["Tokens", s.model_requests ? `${(s.tokens_in ?? 0).toLocaleString("en-IN")} in, ${(s.tokens_out ?? 0).toLocaleString("en-IN")} out (as reported by the server)` : null],
        ["Retries and errors", `${s.retries ?? 0} retries, ${s.errors ?? 0} failed tasks`],
        ["Trigger", data.trigger],
      ]} />
      <Section title="Log">
        <ol className="flex flex-col gap-1 text-sm">{data.log.map((l, i) => <li key={i}><span className="text-muted-foreground">{when(l.at)}</span> {l.msg}</li>)}</ol>
      </Section>
      {!!data.tasks.length && (
        <Section title="Tasks">
          <Table>
            <TableHeader><TableRow><TableHead>Item</TableHead><TableHead>Step</TableHead><TableHead>Status</TableHead><TableHead>Attempts</TableHead></TableRow></TableHeader>
            <TableBody>{data.tasks.map((t) => (
              <TableRow key={t.id}>
                <TableCell className="max-w-[22rem]">
                  {link(t) ? <a className="underline-offset-2 hover:underline" href={link(t)!}>{t.target_title ?? `#${t.target_id}`}</a> : <span>{TASK_LABEL[t.kind] ?? t.kind.replaceAll("_", " ")}</span>}
                  {(t.error || t.note) && <p className={t.status === "failed" ? "text-xs text-(--destructive-text)" : "text-xs text-muted-foreground"}>{t.status === "failed" ? t.error : t.note}</p>}
                </TableCell>
                <TableCell>{t.kind.replace("_", " ")}</TableCell>
                <TableCell>{t.status}</TableCell>
                <TableCell className="tabular-nums">{t.attempts} of {t.max_attempts}</TableCell>
              </TableRow>))}</TableBody>
          </Table>
        </Section>
      )}
      {!!data.calls.length && (
        <Section title="Model requests">
          <Table>
            <TableHeader><TableRow><TableHead>Purpose</TableHead><TableHead>Model that answered</TableHead><TableHead className="text-right">Seconds</TableHead><TableHead className="text-right">Tokens in / out</TableHead><TableHead>Result</TableHead></TableRow></TableHeader>
            <TableBody>{data.calls.map((c, i) => (
              <TableRow key={i}>
                <TableCell>{c.purpose.replaceAll("_", " ")}</TableCell><TableCell>{c.model_served ?? "none"}</TableCell>
                <TableCell className="text-right tabular-nums">{c.duration_ms ? (c.duration_ms / 1000).toFixed(1) : ""}</TableCell>
                <TableCell className="text-right tabular-nums">{c.tokens_in ?? "?"} / {c.tokens_out ?? "?"}</TableCell>
                <TableCell>{c.ok ? (c.finish_reason === "length" ? "Cut off at the limit" : "Answered") : c.error}</TableCell>
              </TableRow>))}</TableBody>
          </Table>
        </Section>
      )}
    </div>
  )
}
