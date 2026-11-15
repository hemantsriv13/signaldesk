import { useState } from "react"
import { ExternalLink, Pill } from "@/components/common"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { api, type Contact, type Followup, type OutreachState, type Tone } from "@/lib/api"
import { day } from "@/lib/format"

export const STATE: Record<OutreachState, [string, Tone]> = {
  drafted: ["Draft, not sent", "neutral"], sending: ["Sending", "warning"], sent: ["Sent", "success"], failed: ["Send failed", "danger"],
  send_unknown: ["Send unclear: check before retrying", "warning"], contacted: ["Sent by you", "success"],
}
// Fixed when the page loads; the server refuses future dates anyway.
const TODAY = new Date().toISOString().slice(0, 10)

/** You send it yourself, then record the date here. Empty means today. */
function MarkSent({ url, label, onDone }: { url: string; label: string; onDone: () => void }) {
  const [at, setAt] = useState("")
  const [error, setError] = useState<string | null>(null)
  const id = url.replace(/\W+/g, "-")
  const save = async () => {
    try { await api.send(url, "POST", { at }); setError(null); onDone() } catch (e) { setError(e instanceof Error ? e.message : String(e)) }
  }
  return (
    <div className="flex flex-wrap items-end gap-2">
      <div className="flex w-40 flex-col gap-1"><Label htmlFor={id} className="text-xs">Date sent (empty: today)</Label>
        <Input id={id} type="date" max={TODAY} value={at} onChange={(e) => setAt(e.target.value)} className="h-8" /></div>
      <Button size="sm" variant="outline" onClick={save}>{label}</Button>
      {error && <p role="alert" className="text-sm text-(--destructive-text)">{error}</p>}
    </div>
  )
}

function FollowupRow({ f, onChange }: { f: Followup; onChange: () => void }) {
  return (
    <li className="flex flex-col gap-1.5">
      <p className="text-xs text-muted-foreground">Day {f.n === 1 ? 5 : 12} follow-up · {f.state === "sent" ? `sent ${day(f.sent_at)}` : `due ${day(f.due_on)}`}</p>
      <blockquote className="rounded-md bg-muted px-3 py-2 text-sm">{f.text}</blockquote>
      {f.state === "drafted" && <div className="flex flex-wrap items-end gap-2"><CopyButton text={f.text} label="Copy follow-up" />
        <MarkSent url={`/api/outreach/followups/${f.id}/sent`} label="Mark follow-up sent" onDone={onChange} /></div>}
    </li>
  )
}

function CopyButton({ text, label }: { text: string; label: string }) {
  const [done, setDone] = useState(false)
  const copy = async () => {
    try { await navigator.clipboard.writeText(text); setDone(true); window.setTimeout(() => setDone(false), 2000) } catch { setDone(false) }
  }
  return <Button size="sm" variant="outline" onClick={copy}>{done ? "Copied" : label}</Button>
}

/** One person, why they were chosen, where they were verified, and the draft for them. */
export function ContactCard({ c, onChange }: { c: Contact; onChange: () => void }) {
  const [open, setOpen] = useState(false)
  const [state, label] = c.state ? [c.state, STATE[c.state][0]] : [null, null]
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-border p-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p><span className="font-medium">{c.name}</span>{c.title && <span className="text-muted-foreground"> · {c.title}</span>}</p>
        {state && <Pill tone={STATE[state][1]}>{label}{(state === "contacted" || state === "sent") && c.sent_at ? ` ${day(c.sent_at)}` : ""}</Pill>}
      </div>
      {c.why && <p className="text-sm">{c.why}</p>}
      <p className="text-xs text-muted-foreground">
        {c.status === "unresolved" ? "Not verified: no page ties this person to the company yet." :
          c.status === "added_by_you" ? "Added by you." : `Verified ${day(c.verified_at)} on the page linked below.`}
        {!c.profile_url && c.status !== "unresolved" && " No public profile was linked there, so none is shown."}
      </p>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        {c.profile_url && <ExternalLink url={c.profile_url}>Open profile</ExternalLink>}
        {c.evidence_url && <ExternalLink url={c.evidence_url}>Where they are named</ExternalLink>}
      </div>
      {c.note_text && (
        <div className="flex flex-col gap-2">
          <p className="text-xs text-muted-foreground">{c.drafted_by === "model" ? "Drafted by the local model." : "Template draft."} Read it before you send it.</p>
          <blockquote className="rounded-md bg-muted px-3 py-2 text-sm">{c.note_text}</blockquote>
          {open && <blockquote className="whitespace-pre-wrap rounded-md bg-muted px-3 py-2 text-sm">{c.message_text}</blockquote>}
          <div className="flex flex-wrap gap-2">
            <CopyButton text={c.note_text} label="Copy note" />
            <Button size="sm" variant="ghost" onClick={() => setOpen(!open)} aria-expanded={open}>{open ? "Hide full message" : "Show full message"}</Button>
            {open && c.message_text && <CopyButton text={c.message_text} label="Copy message" />}
          </div>
          {state === "drafted" && c.outreach_id && <MarkSent url={`/api/outreach/${c.outreach_id}/contacted`} label="Mark sent" onDone={onChange} />}
          {!!c.followups?.length && <ul className="flex flex-col gap-3 border-t border-border pt-2">{c.followups.map((f) => <FollowupRow key={f.id} f={f} onChange={onChange} />)}</ul>}
        </div>
      )}
    </div>
  )
}
