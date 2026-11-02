import { Briefing } from "@/components/briefing"
import { Empty, ListDetail, ListItem, PageHeader, Pill, RunHistoryLink } from "@/components/common"
import { Button } from "@/components/ui/button"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { api, useApi, type Digest } from "@/lib/api"
import { plural, when } from "@/lib/format"
import { go, href, useRoute } from "@/lib/router"

interface Row { id: number; created_at: string; status: string; jobs: number; articles: number; case: boolean; quiet: boolean }

export default function Saved() {
  const route = useRoute()
  const tab = route.params.get("tab") ?? "saved"
  const { data, error, reload } = useApi<{ digests: Row[] }>(`/api/digests?status=${tab}`)
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-8 p-4 sm:p-6">
      <PageHeader title="Saved" line={<>Earlier briefings. Jobs you marked Interested, Investigate or Applied are in the <a className="underline" href={href("jobs", null, { view: "saved" })}>Jobs shortlist</a>.</>}
        action={<RunHistoryLink agent="digest_editor" label="Digest Editor" />} />
      <div className="flex flex-col gap-4">
        <Tabs value={tab} onValueChange={(v) => go("saved", null, { tab: String(v) })}>
          <TabsList><TabsTrigger value="saved">Briefings</TabsTrigger><TabsTrigger value="archived">Archived</TabsTrigger></TabsList>
        </Tabs>
      </div>
      <ListDetail hasSelection={!!route.id} backHref={href("saved", null, { tab })}
        list={data && !data.digests.length ? <Empty title={tab === "saved" ? "No briefings yet" : "Nothing archived"} line={tab === "saved" ? "Briefings appear here after a run." : "Archive a briefing to move it here."} /> : (
          <ul className="min-h-0 flex-1 overflow-y-auto">
            {!data && <li className="p-4 text-sm text-muted-foreground">{error ?? "Loading"}</li>}
            {data?.digests.map((d) => (
              <ListItem key={d.id} selected={route.id === d.id} to={href("saved", d.id, { tab })}>
                <span className="font-medium">{when(d.created_at)}</span>
                <span className="text-sm text-muted-foreground">{d.quiet ? "Quiet day" : `${plural(d.jobs, "job")}, ${plural(d.articles, "article")}${d.case ? ", a case study" : ""}`}</span>
              </ListItem>))}
          </ul>
        )}
        detail={route.id ? <DigestView id={route.id} onChange={reload} /> : <Empty title="Select a briefing" line="Each briefing is kept as it was written, with links to the saved items." />} />
    </div>
  )
}

function DigestView({ id, onChange }: { id: number; onChange: () => void }) {
  const { data, reload } = useApi<Digest>(`/api/digests/${id}`)
  if (!data) return <p className="p-6 text-sm text-muted-foreground">Loading</p>
  const flip = async () => {
    await api.send(`/api/digests/${id}`, "PATCH", { status: data.status === "archived" ? "saved" : "archived" })
    reload()
    onChange()
  }
  return (
    <div className="flex flex-col gap-4 p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-heading text-2xl font-medium">Briefing from {when(data.generated_at)}</h2>
        <div className="flex items-center gap-2">{data.status === "archived" && <Pill>Archived</Pill>}<Button size="sm" variant="outline" onClick={flip}>{data.status === "archived" ? "Restore" : "Archive"}</Button></div>
      </div>
      <p className="text-sm text-muted-foreground">Saved as written. Items may have changed since: open them for the current state.</p>
      <Briefing digest={data} onFeedback={() => {}} />
    </div>
  )
}
