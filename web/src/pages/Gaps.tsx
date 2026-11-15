import { Empty, PageHeader, Section } from "@/components/common"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useApi } from "@/lib/api"
import { href } from "@/lib/router"

interface Item {
  label: string; roles: number; job_ids: number[]; facts_mentioning: string[]; reading: { id: number; title: string }[]
  evidence?: string; roles_with_cited_evidence?: number
}
interface Resp { roles_analysed: number; families: string[]; requirements: Item[]; gaps: Item[] }

function Reading({ items }: { items: Item["reading"] }) {
  if (!items.length) return <span className="text-muted-foreground">–</span>
  return <>{items.map((r) => <a key={r.id} className="block underline-offset-2 hover:underline" href={href("reading", r.id)}>{r.title}</a>)}</>
}

/** What your target roles keep asking for, grouped from saved fit analyses by rule. */
export default function Gaps() {
  const { data, error } = useApi<Resp>("/api/gaps")
  if (error && !data) return <div className="p-6"><Empty title="Could not load" line={error} /></div>
  if (!data) return <p className="p-6 text-sm text-muted-foreground" role="status">Loading</p>
  return (
    <div className="flex flex-col gap-8 p-4 sm:p-6">
      <PageHeader title="Skill gaps" line={`Grouped from the fit analyses of ${data.roles_analysed} open role(s) in your role families. Wording is grouped by shared words, so check the label against the roles.`} />
      {!data.roles_analysed ? <Empty title="No analysed roles yet" line="Fit analyses appear after a sweep with the local model running." /> : (<>
        <Section title="Requirements that recur">
          <Table>
            <TableHeader><TableRow><TableHead>Requirement</TableHead><TableHead className="text-right">Roles</TableHead><TableHead>Your evidence</TableHead><TableHead>Related reading</TableHead></TableRow></TableHeader>
            <TableBody>{data.requirements.map((r) => (
              <TableRow key={r.label}>
                <TableCell className="max-w-[22rem]">{r.label}</TableCell>
                <TableCell className="text-right tabular-nums">{r.roles}</TableCell>
                <TableCell className="text-sm">{r.evidence}{r.facts_mentioning.length ? ` (${r.facts_mentioning.join(", ")})` : ""}</TableCell>
                <TableCell className="text-sm"><Reading items={r.reading} /></TableCell>
              </TableRow>))}</TableBody>
          </Table>
        </Section>
        <Section title="Gaps the analyses named">
          <Table>
            <TableHeader><TableRow><TableHead>Gap</TableHead><TableHead className="text-right">Roles</TableHead><TableHead>Related reading</TableHead></TableRow></TableHeader>
            <TableBody>{data.gaps.map((g) => (
              <TableRow key={g.label}>
                <TableCell className="max-w-[26rem]">{g.label}</TableCell>
                <TableCell className="text-right tabular-nums">{g.roles}</TableCell>
                <TableCell className="text-sm"><Reading items={g.reading} /></TableCell>
              </TableRow>))}</TableBody>
          </Table>
        </Section>
      </>)}
    </div>
  )
}
