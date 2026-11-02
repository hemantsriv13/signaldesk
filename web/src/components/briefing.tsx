import { useState } from "react"
import { ExternalLink, FeedbackSelect, MatchPill, Pill } from "@/components/common"
import type { Digest, DigestItem } from "@/lib/api"

function Item({ item, onFeedback }: { item: DigestItem; onFeedback: () => void }) {
  const [fb, setFb] = useState("")
  return (
    <li className="flex flex-col gap-2 py-4">
      <div className="flex flex-col gap-0.5">
        <a href={item.detail} className="font-medium underline-offset-2 hover:underline">{item.title}</a>
        <span className="text-sm text-muted-foreground">{item.subtitle}</span>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {item.type === "job" && <MatchPill match={item.match} />}
        {item.badges.map((b) => <Pill key={b.text} tone={b.tone}>{b.text}</Pill>)}
      </div>
      {item.summary && item.summary !== "unknown" && <p className="max-w-[70ch] text-[0.95rem]"><span className="text-xs text-muted-foreground">Model summary: </span>{item.summary}</p>}
      <div className="max-w-[70ch] text-sm">
        <p className="font-medium">Why this is here</p>
        <ul className="list-disc ps-5 text-muted-foreground">{item.why.map((w) => <li key={w}>{w}</li>)}</ul>
      </div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <ExternalLink url={item.original_url}>Original</ExternalLink>
        <FeedbackSelect type={item.type} id={item.id} value={fb} onChange={(v) => { setFb(v); onFeedback() }} />
      </div>
    </li>
  )
}

export function Briefing({ digest, onFeedback }: { digest: Digest; onFeedback: () => void }) {
  const sections: [string, DigestItem[]][] = [["Jobs", digest.jobs], ["Case study", digest.case ? [digest.case] : []], ["Reading", digest.articles]]
  return (
    <div className="flex max-w-[78ch] flex-col gap-6">
      {digest.quiet ? <p className="text-sm text-muted-foreground">A quiet day: nothing new matched your preferences.</p>
        : <p className="text-sm text-muted-foreground">Feedback is saved. Items marked not relevant or known stay out of later briefings. It never retrains the model.</p>}
      {sections.filter(([, items]) => items.length).map(([title, items]) => (
        <section key={title} aria-label={title}>
          <h3 className="font-heading text-lg font-medium">{title}</h3>
          <ul className="flex flex-col divide-y divide-border">{items.map((it) => <Item key={`${it.type}${it.id}`} item={it} onFeedback={onFeedback} />)}</ul>
        </section>
      ))}
      {digest.term && (
        <section aria-label="Term">
          <h3 className="font-heading text-lg font-medium">Term: {digest.term.term}</h3>
          <p className="max-w-[70ch] text-[0.95rem]">{digest.term.explanation}</p>
          <p className="text-sm text-muted-foreground">From <a className="underline" href={digest.term.detail}>{digest.term.from_title}</a>. Explained by the local model.</p>
        </section>
      )}
      {digest.action && (
        <section aria-label="Suggested action" className="rounded-lg bg-muted px-4 py-3">
          <h3 className="font-heading text-lg font-medium">Suggested action</h3>
          <p className="text-[0.95rem]">{digest.action.action}</p>
          <p className="text-xs text-muted-foreground">
            About {digest.refs[digest.action.ref]?.split(".")[0] ?? digest.action.ref}.{" "}
            {digest.action.by === "model" ? `Suggested by ${digest.action.model_id}.` : `Suggested by a fixed rule: ${digest.action.reason ?? ""}`}
          </p>
        </section>
      )}
      {!!digest.notes.length && (
        <ul className="flex flex-col gap-1 text-sm text-muted-foreground">{digest.notes.map((n) => <li key={n}>{n}</li>)}</ul>
      )}
    </div>
  )
}

