import { useState } from "react"
import { useStatus } from "@/App"
import { Briefing } from "@/components/briefing"
import { Empty, PageHeader, Section } from "@/components/common"
import { PlayIcon, StopIcon, WarningIcon } from "@/components/icons"
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import { api, type ActiveRun } from "@/lib/api"
import { ago, plural, when } from "@/lib/format"
import { href } from "@/lib/router"

function RunProgress({ run, onCancel }: { run: ActiveRun; onCancel: () => void }) {
  const t = run.tasks
  const total = Object.values(t).reduce((a, b) => a + b, 0)
  const finished = (t.done ?? 0) + (t.cached ?? 0) + (t.failed ?? 0) + (t.cancelled ?? 0)
  const step = run.status === "collecting" ? "Collecting from sources" : total ? `Analysed ${finished} of ${total}` : "Waiting for earlier steps"
  return (
    <li className="flex flex-col gap-1.5 py-2">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <a href={href("runs", run.id)} className="font-medium underline-offset-2 hover:underline">{run.agentName}</a>
        <span className="text-sm text-muted-foreground">{step} · started {ago(run.started_at)}</span>
      </div>
      {run.status !== "collecting" && total > 0 && <Progress value={(finished / total) * 100} aria-label={`${run.agentName} progress`} />}
      <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
        {!!t.failed && <span className="text-(--destructive-text)">{plural(t.failed, "task")} failed</span>}
        {!!run.stats.retries && <span>{plural(run.stats.retries, "retry", "retries")}</span>}
        <Button size="sm" variant="ghost" onClick={onCancel}><StopIcon className="size-3.5" />Cancel run</Button>
      </div>
    </li>
  )
}

export default function Today() {
  const { status, error, reload } = useStatus()
  const [confirm, setConfirm] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const running = !!status?.runs.length

  const runAll = async (regenerate = false) => {
    setMessage(null)
    try {
      const r = regenerate
        ? await api.send<{ started?: number[]; skipped?: string }>("/api/digests/generate", "POST", { regenerate: true, confirm: true })
        : await api.send<{ started?: number[]; skipped?: string }>("/api/runs", "POST", { agent: "all" })
      setMessage(r.skipped ?? null)
    } catch (e) {
      setMessage(e instanceof Error ? e.message : String(e))
    }
    reload()
  }
  const cancel = async (id: number) => { await api.send(`/api/runs/${id}/cancel`, "POST"); reload() }

  if (error && !status) {
    return <div className="p-6"><Empty title="SignalDesk's server is not answering" line={`${error}. Start it with scripts\\start.cmd and reload this page.`} /></div>
  }
  if (!status) return <p className="p-6 text-sm text-muted-foreground" role="status">Loading the current state</p>
  const c = status?.counts
  const digest = status?.latestDigest
  return (
    <div className="flex flex-col gap-8 p-4 sm:p-6">
      <PageHeader title="Today" line="Your latest briefing and what the agents are doing."
        action={<Button onClick={() => runAll()} disabled={running || !status}><PlayIcon className="size-4" />{running ? "Running" : "Run now"}</Button>} />
      {message && <p role="status" className="text-sm text-(--warning-text)">{message}</p>}

      {status && (
        <section aria-label="Current state" className="grid grid-cols-1 gap-x-8 gap-y-4 border-y border-border py-4 text-sm md:grid-cols-3">
          <div className="flex flex-col gap-1">
            <span className="text-muted-foreground">Model</span>
            <span className="font-medium">{status.model.ready ? `Ready: ${status.model.configured}` : status.model.reachable ? "A different model is running" : "Offline"}</span>
            {!status.model.ready && <span className="text-xs text-muted-foreground">{status.model.message} Collection and saved results still work.</span>}
          </div>
          <div className="flex flex-col gap-1">
            <span className="text-muted-foreground">New since the last run</span>
            <span><a className="font-medium underline-offset-2 hover:underline" href={href("jobs")}>{plural(c!.newMatches, "matching job")}</a>
              {" · "}<a className="underline-offset-2 hover:underline" href={href("jobs", null, { view: "review" })}>{c!.review} to review</a></span>
          </div>
          <div className="flex flex-col gap-1">
            <span className="text-muted-foreground">Waiting</span>
            <span>
              {status.queue.queued + status.queue.running ? `${plural(status.queue.queued + status.queue.running, "item")} pending analysis` : "No analysis pending"}
              {!!status.queue.failed && <> · <a className="text-(--destructive-text) underline" href={href("runs")}>{status.queue.failed} failed</a></>}
            </span>
          </div>
        </section>
      )}

      {!!status?.failures.length && (
        <div role="alert" className="flex flex-col gap-1 rounded-lg bg-(--warning-tint) px-4 py-3 text-sm">
          <p className="flex items-center gap-2 font-medium"><WarningIcon className="size-4 shrink-0" />{plural(status.failures.length, "source")} failed on the last check</p>
          <p>{status.failures.slice(0, 3).map((f) => f.name).join(", ")}{status.failures.length > 3 ? ` and ${status.failures.length - 3} more` : ""}. Their saved results are unchanged. <a href={href("sources")} className="underline">See Sources</a></p>
        </div>
      )}

      {running && (
        <Section title="Agents at work">
          <ul className="flex flex-col divide-y divide-border">{status!.runs.map((r) => <RunProgress key={r.id} run={r} onCancel={() => cancel(r.id)} />)}</ul>
        </Section>
      )}

      <Section title={digest ? `Briefing from ${when(digest.created_at ?? digest.generated_at)}` : "Briefing"}
        aside={digest && <Button size="sm" variant="outline" disabled={running} onClick={() => setConfirm(true)}>Regenerate</Button>}>
        {digest ? <Briefing digest={digest} onFeedback={reload} /> : status && (
          <Empty title={c!.everCollected ? "No briefing yet" : "Nothing collected yet"}
            line={c!.everCollected ? "Run now to compose one from what has been collected." : "Run now to check the employer boards and feeds in Sources, analyse what matches, and write your first briefing."} />
        )}
      </Section>

      <AlertDialog open={confirm} onOpenChange={setConfirm}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Regenerate the briefing?</AlertDialogTitle>
            <AlertDialogDescription>
              This checks every source again and runs the local model on new or changed items before writing a new briefing. Saved analyses are reused. The current briefing stays in Saved.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Keep this briefing</AlertDialogCancel>
            <AlertDialogAction onClick={() => runAll(true)}>Collect and regenerate</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
