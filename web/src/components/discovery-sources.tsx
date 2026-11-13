import { useState } from "react"
import { Pill, Section } from "@/components/common"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { Textarea } from "@/components/ui/textarea"
import { api, useApi, type SourceInfo, type Tone } from "@/lib/api"
import { ago, when } from "@/lib/format"

const MODE_TONE: Record<SourceInfo["mode"], Tone> = { automatic: "success", import_assisted: "neutral", needs_setup: "warning", unavailable: "danger", off: "neutral" }

/** Funding and listing sources beyond employer boards, with their real mode and last result. */
export function DiscoverySources() {
  const { data, reload } = useApi<{ sources: SourceInfo[] }>("/api/sweep")
  const extra = data?.sources.filter((s) => s.kind !== "ats") ?? []
  return (
    <Section title="Discovery sources">
      <p className="max-w-[80ch] text-sm text-muted-foreground">Each source shows how it is collected and whether its last check worked.</p>
      <ul className="flex flex-col divide-y divide-border rounded-lg border border-border">{extra.map((s) => <SourceRow key={s.key} s={s} onSaved={reload} />)}</ul>
    </Section>
  )
}

function SourceRow({ s, onSaved }: { s: SourceInfo; onSaved: () => void }) {
  const [url, setUrl] = useState(s.url ?? "")
  const [error, setError] = useState<string | null>(null)
  const [text, setText] = useState("")
  const [result, setResult] = useState<string | null>(null)
  const save = async (change: { enabled?: boolean; url?: string }) => {
    try { await api.send(`/api/sources/registry/${s.key}`, "PATCH", change); setError(null); onSaved() } catch (e) { setError(e instanceof Error ? e.message : String(e)) }
  }
  const importNow = async () => {
    setResult("Reading")
    try {
      const r = await api.send<Record<string, number>>("/api/imports/listings", "POST", { source: s.key, text })
      setResult(`${r.read} read: ${r.merged ?? 0} matched to employer boards, ${(r.unverified ?? 0) + (r.ambiguous ?? 0)} kept as unverified, ` +
        `${r.already ?? 0} already known${r.needs_details ? `, ${r.needs_details} need a title and company` : ""}.`)
      setText(""); onSaved()
    } catch (e) { setResult(e instanceof Error ? e.message : String(e)) }
  }
  const counts = Object.entries(s.counts).filter(([k, v]) => typeof v === "number" && k !== "error").map(([k, v]) => `${v} ${k.replace(/_/g, " ")}`).join(", ")
  return (
    <li className="flex flex-col gap-2 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2"><span className="font-medium">{s.name}</span><Pill tone={MODE_TONE[s.mode]}>{s.modeLabel}</Pill></div>
        <label className="flex items-center gap-2 text-sm"><Switch checked={s.enabled !== false} onCheckedChange={(v) => save({ enabled: !!v })} />On</label>
      </div>
      {s.note && <p className="max-w-[80ch] text-sm text-muted-foreground">{s.note}</p>}
      <p className="text-sm">
        {s.mode === "unavailable" ? <span className="text-(--destructive-text)">Failing since {when(s.status.last_error_at)}: {s.status.last_error}</span> :
          s.status.last_success_at ? `Worked ${ago(s.status.last_success_at)}${counts ? `: ${counts}` : ""}` : "Not run yet"}
      </p>
      {s.kind !== "import" && (
        <div className="flex flex-wrap items-end gap-2">
          <div className="flex w-full max-w-xl flex-col gap-1"><Label htmlFor={`url-${s.key}`}>Page address</Label>
            <Input id={`url-${s.key}`} type="url" placeholder="https://" value={url} onChange={(e) => setUrl(e.target.value)} /></div>
          <Button variant="outline" onClick={() => save({ url })} disabled={url === (s.url ?? "")}>Save address</Button>
        </div>
      )}
      {s.group === "jobs" && s.kind !== "ats" && (
        <details className="text-sm">
          <summary className="cursor-pointer text-(--primary-text)">Import saved listings</summary>
          <div className="mt-2 flex max-w-2xl flex-col gap-2">
            <Label htmlFor={`imp-${s.key}`}>Listing URLs (one per line), a CSV export with a header row, or JSON</Label>
            <Textarea id={`imp-${s.key}`} rows={4} value={text} onChange={(e) => setText(e.target.value)} />
            <p className="text-xs text-muted-foreground">Include title and company columns when you have them. Each listing is matched to the employer's own job board; unmatched ones stay unverified.</p>
            <Button className="w-fit" onClick={importNow} disabled={!text.trim()}>Import</Button>
            {result && <p role="status" className="text-sm">{result}</p>}
          </div>
        </details>
      )}
      {error && <p role="alert" className="text-sm text-(--destructive-text)">{error}</p>}
    </li>
  )
}
