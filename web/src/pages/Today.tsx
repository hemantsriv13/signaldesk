import { useEffect, useState } from "react"
import { useStatus } from "@/App"
import { Briefing } from "@/components/briefing"
import { Empty, ExternalLink, FreshnessPill, LOCATION_TONE, PageHeader, Pill, Section } from "@/components/common"
import { NativeSelect } from "@/components/ui/native-select"
import { PlayIcon, StopIcon, WarningIcon } from "@/components/icons"
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import { api, useApi, type ActiveRun, type FundingEvent, type SourceInfo } from "@/lib/api"
import { ago, day, plural, when } from "@/lib/format"
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

function sweepLine(s: Record<string, number>): string {
  const parts = [`${s.new ?? 0} new`, `${s.updated ?? 0} updated`, `${s.duplicates ?? 0} matched to known openings`]
  if (s.funding_new) parts.push(`${s.funding_new} funding rounds`)
  if (s.failed_sources) parts.push(`${s.failed_sources} sources failed`)
  return parts.join(", ")
}

interface TopJob {
  id: number; title: string; employer: string; location_raw: string | null; location_class: string; location_label: string; family_labels: string[]
  comp_band: string; comp_note: string; apply_url: string | null; official_url: string | null; first_seen_at: string; published_at: string | null
  funded_on: string | null; match: string | null; reason: string; evidence: string | null; background: string | null; gap: string | null
  verified_hours_ago: number | null
}
interface FundedRow { id: number; name: string; latest: FundingEvent | null; opening_state: string; openings: { matching: number } }

/** The three questions: what to apply to, which funded startups to watch, who to contact. */
function Answers() {
  const { status } = useStatus()
  const { data: top, reload: r1 } = useApi<{ jobs: TopJob[] }>("/api/top?limit=3")
  const { data: funded, reload: r2 } = useApi<{ startups: FundedRow[] }>("/api/funding?window=90&india=linked")
  const { data: out, reload: r3 } = useApi<{ items: { id: number; name: string; company: string; job_title: string | null; job_id: number | null }[]; counts: Record<string, number> }>("/api/outreach?state=drafted")
  useEffect(() => { r1(); r2(); r3() }, [status?.sweep.last?.finished_at, status?.counts.matches]) // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div className="grid gap-8 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
      <Section title="Worth applying to today" aside={<a className="text-sm text-(--primary-text) underline underline-offset-2" href={href("jobs")}>All matches</a>}>
        {top && !top.jobs.length ? <p className="text-sm text-muted-foreground">No open Bengaluru or India-remote role in your families right now. Uncertain locations wait in To review.</p> : (
          <ul className="flex flex-col gap-3">{top?.jobs.map((j) => (
            <li key={j.id} className="flex flex-col gap-2 rounded-lg border border-border p-4">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <a href={href("jobs", j.id)} className="font-medium underline-offset-2 hover:underline">{j.title}</a>
                <ExternalLink url={j.apply_url ?? j.official_url}>Apply</ExternalLink>
              </div>
              <p className="text-sm text-muted-foreground">{j.employer} · {j.location_raw || "location not stated"}</p>
              <div className="flex flex-wrap gap-1.5">
                <Pill tone={LOCATION_TONE[j.location_class] ?? "neutral"}>{j.location_label}</Pill>
                <Pill>{j.family_labels.join(" + ")}</Pill>
                <FreshnessPill hours={j.verified_hours_ago} />
              </div>
              <p className="text-sm">{j.reason}{j.match ? ` · model: ${j.match}` : " · fit not analysed yet"}</p>
              {j.evidence && <p className="text-sm text-muted-foreground">From the posting: “{j.evidence}”</p>}
              {j.background && <p className="text-sm text-muted-foreground">From your background: {j.background}</p>}
              {j.gap && <p className="text-sm text-(--warning-text)">Gap: {j.gap}</p>}
              <p className="text-xs text-muted-foreground">{j.comp_note}{j.funded_on ? ` · funding announced ${day(j.funded_on)} (not part of the ranking)` : ""}</p>
            </li>))}</ul>
        )}
      </Section>
      <div className="flex flex-col gap-8">
        <Section title="Recently funded, India-linked" aside={<a className="text-sm text-(--primary-text) underline underline-offset-2" href={href("funded", null, { window: "90" })}>All</a>}>
          {funded && !funded.startups.length ? <p className="text-sm text-muted-foreground">No dated rounds in the last 90 days yet. Set up announcement sources under Sources.</p> : (
            <ul className="flex flex-col gap-2 text-sm">{funded?.startups.slice(0, 4).map((s) => (
              <li key={s.id}><a href={href("funded", s.id, { window: "90" })} className="font-medium underline-offset-2 hover:underline">{s.name}</a>
                <span className="text-muted-foreground"> · {s.latest ? `${s.latest.investor ?? "investor not named"}, ${day(s.latest.announced_on)}` : ""} · {s.opening_state}</span></li>))}</ul>
          )}
        </Section>
        <Section title="Ready to contact" aside={<a className="text-sm text-(--primary-text) underline underline-offset-2" href={href("outreach")}>Outreach</a>}>
          {out && !out.items.length ? <p className="text-sm text-muted-foreground">No drafts waiting. Mark a role Interested, and the next run finds contacts for it.</p> : (
            <ul className="flex flex-col gap-2 text-sm">{out?.items.slice(0, 3).map((o) => (
              <li key={o.id}><span className="font-medium">{o.name}</span><span className="text-muted-foreground"> · {o.company}{o.job_title ? `, for ${o.job_title}` : ""}</span></li>))}</ul>
          )}
        </Section>
      </div>
    </div>
  )
}

/** Source status, kept behind a details control. Failed and empty are shown differently. */
function SourceHealth({ sources }: { sources: SourceInfo[] }) {
  const bad = sources.filter((s) => s.mode === "unavailable" || s.mode === "needs_setup")
  return (
    <details className="rounded-lg border border-border p-4 text-sm">
      <summary className="cursor-pointer font-medium">Sources: {sources.filter((s) => s.mode === "automatic").length} automatic, {sources.filter((s) => s.mode === "import_assisted").length} import-assisted{bad.length ? `, ${bad.length} need attention` : ""}</summary>
      <ul className="mt-3 flex flex-col gap-2">{sources.map((s) => (
        <li key={s.key} className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <span className="font-medium">{s.name}</span>
          <Pill tone={s.mode === "automatic" ? "success" : s.mode === "unavailable" ? "danger" : s.mode === "off" ? "neutral" : "warning"}>{s.modeLabel}</Pill>
          <span className="text-muted-foreground">
            {s.mode === "unavailable" ? `Failing since ${when(s.status.last_error_at)}: ${s.status.last_error}` :
              s.status.last_success_at ? `Worked ${ago(s.status.last_success_at)}` : s.mode === "needs_setup" ? "Add its page address in Sources" : "Not run yet"}
          </span>
        </li>))}</ul>
      <p className="mt-3"><a href={href("sources")} className="text-(--primary-text) underline underline-offset-2">Set up sources and import listings</a></p>
    </details>
  )
}

export default function Today() {
  const { status, error, reload } = useStatus()
  const { data: sources } = useApi<{ sources: SourceInfo[] }>("/api/sweep", 60000)
  const [confirm, setConfirm] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const running = !!status?.runs.length

  const [scope, setScope] = useState("full")
  const runAll = async (regenerate = false) => {
    setMessage(null)
    try {
      const r = regenerate
        ? await api.send<{ started?: number[]; skipped?: string }>("/api/digests/generate", "POST", { regenerate: true, confirm: true })
        : await api.send<{ started?: number[]; skipped?: string }>("/api/sweep", "POST", { scope })
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
      <div className="welcome-card rounded-2xl px-5 py-4">
        <p className="font-heading text-xl">Less noise. More possibility.</p>
        <p className="mt-1 text-sm">Today's jobs, useful reads and real AI work.</p>
      </div>
      <PageHeader title="Today"
        action={<>
          <NativeSelect aria-label="What to refresh" value={scope} onChange={(e) => setScope(e.target.value)} className="h-9 w-48 text-sm" disabled={running}>
            <option value="full">Everything</option><option value="jobs">Jobs and contacts</option><option value="funding">Funded startups</option>
            <option value="contacts">Contacts only</option><option value="reading">Reading</option>
            {sources?.sources.filter((s) => s.mode === "automatic" || s.mode === "unavailable").map((s) => <option key={s.key} value={`source:${s.key}`}>Only {s.name}</option>)}
          </NativeSelect>
          <Button onClick={() => runAll()} disabled={running || !status}><PlayIcon className="size-4" />{running ? "Running" : "Run now"}</Button></>} />
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
            <span className="text-muted-foreground">Last refresh</span>
            <span>
              {status.sweep.last ? `${when(status.sweep.last.finished_at)}: ${sweepLine(status.sweep.last.summary)}` : "No sweep has finished yet"}
              {status.schedule.next_run ? ` · next ${when(status.schedule.next_run)}` : ""}
            </span>
            <span className="text-xs text-muted-foreground">
              {status.queue.queued + status.queue.running ? `${plural(status.queue.queued + status.queue.running, "item")} pending analysis` : "No analysis pending"}
              {!!status.queue.failed && <> · <a className="text-(--destructive-text) underline" href={href("runs")}>{status.queue.failed} failed</a></>}
            </span>
          </div>
        </section>
      )}

      <Answers />

      {sources && <SourceHealth sources={sources.sources} />}

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
