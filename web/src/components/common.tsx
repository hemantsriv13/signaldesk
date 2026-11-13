import type { ReactNode } from "react"
import { ArrowSquareOutIcon } from "@/components/icons"
import { Badge } from "@/components/ui/badge"
import { NativeSelect } from "@/components/ui/native-select"
import { api, type Tone } from "@/lib/api"
import { ago } from "@/lib/format"
import { href } from "@/lib/router"
import { cn } from "@/lib/utils"

export function PageHeader({ title, line, action, sans }: { title: string; line?: ReactNode; action?: ReactNode; sans?: boolean }) {
  return (
    <header className="flex flex-wrap items-end justify-between gap-4">
      <div className="flex min-w-0 flex-col gap-1">
        <h1 className={cn("text-2xl leading-tight", sans ? "font-sans font-semibold tracking-tight" : "font-heading font-medium")}>{title}</h1>
        {line && <p className="max-w-[70ch] text-sm text-muted-foreground">{line}</p>}
      </div>
      {action && <div className="flex flex-wrap items-center gap-2">{action}</div>}
    </header>
  )
}

const TONE: Record<Tone, "default" | "warning" | "destructive" | "success"> = { neutral: "default", warning: "warning", danger: "destructive", success: "success" }

export function Pill({ tone = "neutral", children, title }: { tone?: Tone; children: ReactNode; title?: string }) {
  return <Badge variant={TONE[tone]} title={title} className="max-w-full truncate">{children}</Badge>
}

export function ExternalLink({ url, children, className }: { url: string | null | undefined; children: ReactNode; className?: string }) {
  if (!url) return null
  return (
    <a href={url} target="_blank" rel="noopener noreferrer" className={cn("inline-flex items-center gap-1 text-sm text-(--primary-text) underline underline-offset-2", className)}>
      {children}
      <ArrowSquareOutIcon className="size-3.5 shrink-0" />
      <span className="sr-only">(opens the original site in a new tab)</span>
    </a>
  )
}

/** A passage copied from the source, with whether SignalDesk found it there. */
export function Evidence({ quote, found }: { quote: string | null | undefined; found?: boolean }) {
  if (!quote || quote === "unknown") return <p className="text-xs text-muted-foreground">No supporting passage</p>
  return (
    <figure className="flex flex-col gap-1 rounded-md bg-(--quote) px-3 py-2 text-(--quote-foreground)">
      <blockquote className="font-heading text-[0.95rem] italic leading-snug">“{quote}”</blockquote>
      {found !== undefined && (
        <figcaption className={cn("text-xs", found ? "text-muted-foreground" : "text-(--warning-text)")}>
          {found ? "Found in the source text" : "Not found in the source text: treat with care"}
        </figcaption>
      )}
    </figure>
  )
}

export function ModelNote({ model, at, version, notes, coverage }: {
  model: string; at: string; version: string; notes: string[]; coverage?: { chars_sent: number; chars_total: number; complete: boolean }
}) {
  return (
    <div className="flex flex-col gap-1 text-xs text-muted-foreground">
      <p>Written by the local model {model} {ago(at)} ({version}). Checked by rules; not reviewed by a person.</p>
      {coverage && !coverage.complete && (
        <p className="text-(--warning-text)">Read {coverage.chars_sent.toLocaleString("en-IN")} of {coverage.chars_total.toLocaleString("en-IN")} characters: the model's context window is small.</p>
      )}
      {notes.map((n) => <p key={n} className="text-(--warning-text)">{n}</p>)}
    </div>
  )
}

export function Section({ title, children, className, aside }: { title: string; children: ReactNode; className?: string; aside?: ReactNode }) {
  return (
    <section className={cn("flex flex-col gap-3", className)}>
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="text-base font-semibold">{title}</h2>
        {aside}
      </div>
      {children}
    </section>
  )
}

export function Facts({ rows }: { rows: [string, ReactNode][] }) {
  return (
    <dl className="grid grid-cols-[minmax(8rem,auto)_1fr] gap-x-4 gap-y-1.5 text-sm">
      {rows.filter(([, v]) => v !== null && v !== undefined && v !== "").map(([k, v]) => (
        <div key={k} className="contents">
          <dt className="text-muted-foreground">{k}</dt>
          <dd className="min-w-0 break-words">{v}</dd>
        </div>
      ))}
    </dl>
  )
}

/**
 * List on the left, the selected record on the right. Each pane scrolls on its own so the list
 * keeps its place. Below the large breakpoint only one pane shows at a time.
 */
export function ListDetail({ list, detail, hasSelection, backHref, backLabel = "Back to the list", onBack }: {
  list: ReactNode; detail: ReactNode; hasSelection: boolean; backHref: string; backLabel?: string; onBack?: () => void
}) {
  return (
    <div className="grid min-h-[32rem] flex-1 grid-cols-1 gap-4 lg:grid-cols-[minmax(20rem,26rem)_minmax(0,1fr)]">
      <div className={cn("min-h-0 flex-col overflow-hidden rounded-xl border border-border bg-card lg:flex", hasSelection ? "hidden" : "flex")}>{list}</div>
      <div className={cn("min-h-0 flex-col lg:flex", hasSelection ? "flex" : "hidden")}>
        {hasSelection && (
          <a href={backHref} onClick={onBack} className="mb-3 inline-flex min-h-11 items-center text-sm font-medium text-(--primary-text) underline underline-offset-2 lg:hidden">{backLabel}</a>
        )}
        <div className="rounded-xl border border-border bg-background lg:min-h-0 lg:flex-1 lg:overflow-y-auto">{detail}</div>
      </div>
    </div>
  )
}

export function ListItem({ selected, to, children, onClick }: { selected: boolean; to: string; children: ReactNode; onClick?: () => void }) {
  return (
    <li>
      <a href={to} onClick={onClick} aria-current={selected ? "true" : undefined}
        className={cn("flex flex-col gap-1 border-b border-border px-4 py-3 outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset",
          selected ? "bg-(--row-selected) text-(--row-selected-foreground) shadow-[inset_3px_0_0_var(--row-indicator)]" : "hover:bg-(--row-hover)")}>
        {children}
      </a>
    </li>
  )
}

export function Empty({ title, line, action }: { title: string; line: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-start gap-2 p-6">
      <p className="font-medium">{title}</p>
      <p className="max-w-[60ch] text-sm text-muted-foreground">{line}</p>
      {action}
    </div>
  )
}

/** One feedback control per item. The verdict ranks later briefings and can suggest a preference change. */
export function FeedbackSelect({ type, id, value, onChange }: { type: string; id: number; value: string; onChange: (v: string) => void }) {
  const change = async (next: string) => {
    const itemType = type === "case" ? "article" : type
    if (value) await api.send("/api/feedback", "POST", { item_type: itemType, item_id: id, verdict: value, on: false })
    if (next) await api.send("/api/feedback", "POST", { item_type: itemType, item_id: id, verdict: next, on: true })
    onChange(next)
  }
  return (
    <div className="w-44">
      <NativeSelect aria-label="Feedback on this item" value={value} onChange={(e) => change(e.target.value)} className="h-8 text-sm">
        <option value="">Feedback</option><option value="useful">Useful</option><option value="not_relevant">Not relevant</option>
        <option value="known">Already known</option><option value="too_technical">Too technical</option>
      </NativeSelect>
    </div>
  )
}

export function BasisPill({ basis }: { basis: string }) {
  if (basis === "full") return <Pill tone="success">Full text</Pill>
  if (basis === "excerpt") return <Pill tone="warning">Excerpt only</Pill>
  return <Pill tone="warning">Title only</Pill>
}

export function FreshnessPill({ hours }: { hours: number | null | undefined }) {
  if (hours === null || hours === undefined) return <Pill tone="warning">Never verified</Pill>
  if (hours > 48) return <Pill tone="warning">Verified {Math.round(hours / 24)} days ago</Pill>
  return <Pill>Verified {hours < 1 ? "within the hour" : `${Math.round(hours)} h ago`}</Pill>
}

export const LOCATION_TONE: Record<string, Tone> = {
  bengaluru: "success", remote_india: "success", remote_unclear: "warning", india_unspecified: "warning", unknown: "warning",
  india_other: "neutral", remote_other: "neutral", other: "neutral",
}

export function MatchPill({ match, pending }: { match: string | null | undefined; pending?: boolean }) {
  if (pending) return <Pill>Analysis queued</Pill>
  if (!match) return <Pill>Not analysed</Pill>
  const tone: Tone = match === "potential match" ? "success" : match === "not a match" ? "danger" : match === "weak match" ? "warning" : "neutral"
  return <Pill tone={tone} title="The local model's reading of the requirements against your profile">{match === "unknown" ? "Model: fit unknown" : `Model: ${match}`}</Pill>
}

export function RunHistoryLink({ agent, label }: { agent: string; label: string }) {
  return <a href={href("runs", null, { agent })} className="inline-flex min-h-11 items-center text-sm text-(--primary-text) underline underline-offset-2">{label} run history</a>
}
