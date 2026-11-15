import { useEffect } from "react"
import { Section } from "@/components/common"
import { useApi, type PipelineAction } from "@/lib/api"
import { href } from "@/lib/router"

/** At most five concrete actions for today. Rules choose them (signaldesk/pipeline.py); nothing here is written by the model. */
export function TodaysActions({ refreshKey }: { refreshKey?: unknown }) {
  const { data, reload } = useApi<{ actions: PipelineAction[] }>("/api/actions")
  useEffect(() => { reload() }, [refreshKey]) // eslint-disable-line react-hooks/exhaustive-deps
  const actions = data?.actions ?? []
  return (
    <Section title="Today's actions" aside={<a className="text-sm text-(--primary-text) underline underline-offset-2" href={href("pipeline")}>Pipeline</a>}>
      {!data ? <p className="text-sm text-muted-foreground" role="status">Loading</p> : actions.length ? (
        <ol className="flex flex-col divide-y divide-border rounded-lg border border-border">{actions.map((a) => (
          <li key={`${a.kind}-${a.job_id}-${a.outreach_id ?? ""}`} className="flex flex-col gap-0.5 p-3">
            <a className="font-medium underline-offset-2 hover:underline" href={href("jobs", a.job_id)}>{a.text}</a>
            <span className="text-sm text-muted-foreground">{a.why}</span>
          </li>))}</ol>
      ) : <p className="text-sm text-muted-foreground">Nothing needs you right now. Shortlist a role in Jobs to start your pipeline.</p>}
    </Section>
  )
}
