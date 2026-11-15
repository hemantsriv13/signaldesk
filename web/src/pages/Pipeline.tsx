import { Empty, PageHeader, Pill, Section } from "@/components/common"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useApi, type PipelineSummary } from "@/lib/api"
import { day } from "@/lib/format"
import { href } from "@/lib/router"

const MAIN = ["Shortlisted", "Applied", "Contact made", "Reply", "Interview", "Offer"]
const pct = (r: number | null) => (r === null ? "–" : `${Math.round(r * 100)}%`)
const days = (d: number | null | undefined) => (d === null || d === undefined ? "–" : `${d}`)

/** Where each application stands, how the funnel converts, and what is waiting on you. All numbers come from rules. */
export default function Pipeline() {
  const { data, error } = useApi<PipelineSummary>("/api/pipeline")
  if (error && !data) return <div className="p-6"><Empty title="Could not load the pipeline" line={error} /></div>
  if (!data) return <p className="p-6 text-sm text-muted-foreground" role="status">Loading</p>
  const inPipeline = data.items.length
  const undated = data.items.some((i) => i.last_event && !i.last_event.dated)
  return (
    <div className="flex flex-col gap-8 p-4 sm:p-6">
      <PageHeader title="Pipeline" line="Every role you shortlisted, from first look to offer. Move a role on from its page in Jobs." />

      {!inPipeline ? (
        <Empty title="No roles in your pipeline yet" line="Open a role in Jobs and shortlist it. It appears here with the date, and each later step you record." />
      ) : (<>
        <Section title="Needs you">
          {data.needs_action.length ? (
            <ul className="flex flex-col divide-y divide-border rounded-lg border border-border">{data.needs_action.map((n) => (
              <li key={`${n.kind}-${n.job_id}-${n.outreach_id ?? ""}`} className="flex flex-col gap-0.5 p-3">
                <a className="font-medium underline-offset-2 hover:underline" href={href("jobs", n.job_id)}>{n.title} · {n.employer}</a>
                <span className="text-sm text-muted-foreground">{n.why}</span>
              </li>))}</ul>
          ) : <p className="text-sm text-muted-foreground">Nothing is waiting on you: no reply to answer, no application 7+ days old without a contact, no draft left unsent for 3+ days.</p>}
        </Section>

        <Section title="Stages">
          <Table>
            <TableHeader><TableRow>
              <TableHead>Stage</TableHead><TableHead className="text-right">Now</TableHead><TableHead className="text-right">Ever reached</TableHead>
              <TableHead className="text-right">Went on to the next stage</TableHead><TableHead className="text-right">Median days in stage</TableHead>
            </TableRow></TableHeader>
            <TableBody>
              {data.stages.map((s) => {
                const conv = data.conversion.find((c) => c.from === s)
                return (
                  <TableRow key={s}>
                    <TableCell className="font-medium">{s}</TableCell>
                    <TableCell className="text-right tabular-nums">{data.counts[s]}</TableCell>
                    <TableCell className="text-right tabular-nums">{data.reached[s]}</TableCell>
                    <TableCell className="text-right tabular-nums">{conv ? `${conv.moved} of ${conv.reached} (${pct(conv.rate)})` : "–"}</TableCell>
                    <TableCell className="text-right tabular-nums">{MAIN.includes(s) ? days(data.median_days[s]) : "–"}</TableCell>
                  </TableRow>)
              })}
            </TableBody>
          </Table>
          <p className="max-w-[75ch] text-sm text-muted-foreground">
            "Went on" counts roles that reached the next stage, in any order. Days in stage run from the date you gave to the next step, or to today
            if the role is still there.{undated ? " Roles you marked before the pipeline existed have no known date, so they count in the stages but not in the days." : ""}
          </p>
        </Section>

        <Section title="Applications per week">
          <Table>
            <TableHeader><TableRow>{data.weeks.map((w) => <TableHead key={w.week_of} className="text-right">{day(w.week_of).replace(/ \d{4}$/, "")}</TableHead>)}</TableRow></TableHeader>
            <TableBody><TableRow>{data.weeks.map((w) => <TableCell key={w.week_of} className="text-right tabular-nums">{w.applications}</TableCell>)}</TableRow></TableBody>
          </Table>
          <p className="text-sm text-muted-foreground">Weeks start on Monday; the last column is this week.</p>
        </Section>

        <Section title="Your roles">
          <Table>
            <TableHeader><TableRow><TableHead>Role</TableHead><TableHead>Stage</TableHead><TableHead>Since</TableHead><TableHead>Your note</TableHead></TableRow></TableHeader>
            <TableBody>{data.items.map((i) => (
              <TableRow key={i.id}>
                <TableCell className="max-w-[22rem]"><a className="font-medium underline-offset-2 hover:underline" href={href("jobs", i.id)}>{i.title}</a>
                  <span className="block text-xs text-muted-foreground">{i.employer}</span></TableCell>
                <TableCell><Pill tone={i.stage === "Offer" ? "success" : "neutral"}>{i.stage}</Pill></TableCell>
                <TableCell className="whitespace-nowrap">{i.last_event ? (i.last_event.dated ? day(i.last_event.at) : "date unknown") : "–"}</TableCell>
                <TableCell className="max-w-[28rem] text-sm text-muted-foreground">{i.last_event?.note ?? ""}</TableCell>
              </TableRow>))}</TableBody>
          </Table>
        </Section>
      </>)}
    </div>
  )
}
