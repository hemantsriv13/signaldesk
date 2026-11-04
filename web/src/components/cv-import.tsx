import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"

interface Preview { text: string; candidates: string[]; warnings: string[]; filename: string; max_facts: number }

export function CvImport({ onUse }: { onUse: (facts: string[]) => void }) {
  const [preview, setPreview] = useState<Preview | null>(null)
  const [selected, setSelected] = useState<number[]>([])
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [text, setText] = useState("")
  const load = async (body: Blob | string, filename: string) => {
    setBusy(true); setError(null); setPreview(null); setMessage(null); setSelected([])
    try {
      const response = await fetch(`/api/profile/cv-preview?filename=${encodeURIComponent(filename)}`, {
        method: "POST", headers: { "content-type": "application/octet-stream" }, body,
      })
      const data = await response.json()
      if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Could not read the CV.")
      setPreview(data); setText(data.text)
    } catch (e) { setError(e instanceof Error ? e.message : String(e)) }
    finally { setBusy(false) }
  }
  return <div className="flex max-w-3xl flex-col gap-3 rounded-lg border p-4">
    <h3 className="text-sm font-semibold">Match jobs using your CV</h3>
    <p className="text-sm text-muted-foreground">Upload a text PDF, DOCX or TXT (up to 5 MB), or paste your CV. Extraction runs locally. Choose the facts to use, review them below, then Save profile. Your existing facts are replaced only when you save.</p>
    <Label htmlFor="cv-file">CV file</Label>
    <Input id="cv-file" type="file" accept=".pdf,.docx,.txt" disabled={busy} onChange={(e) => {
      const file = e.target.files?.[0]
      if (file) { if (file.size > 5 * 1024 * 1024) setError("Choose a CV smaller than 5 MB."); else void load(file, file.name) }
      e.target.value = ""
    }} />
    <Label htmlFor="cv-text">CV text (edit or split long paragraphs before extracting again)</Label>
    <Textarea id="cv-text" rows={5} value={text} maxLength={60000} onChange={(e) => setText(e.target.value)} />
    <Button className="w-fit" variant="outline" disabled={busy || !text.trim()} onClick={() => load(text, "pasted-cv.txt")}>{busy ? "Extracting…" : "Extract facts from text"}</Button>
    {busy && <p role="status">Reading your CV locally…</p>}
    {error && <p role="alert" className="text-sm text-(--destructive-text)">{error}</p>}
    {message && <p role="status" className="text-sm">{message}</p>}
    {preview && <>
      {preview.warnings.map((warning) => <p key={warning} className="text-sm text-muted-foreground">{warning}</p>)}
      <p className="text-sm font-medium">Selected {selected.length} / {preview.max_facts} facts from {preview.filename}</p>
      <ul className="flex max-h-80 flex-col gap-3 overflow-y-auto pr-2">{preview.candidates.map((fact, i) => <li key={i}>
        <label className="flex items-start gap-2 text-sm"><Checkbox checked={selected.includes(i)} disabled={!selected.includes(i) && selected.length >= preview.max_facts} onCheckedChange={() => setSelected((old) => old.includes(i) ? old.filter((n) => n !== i) : [...old, i])} /><span>{fact}</span></label>
      </li>)}</ul>
      <Button className="w-fit" disabled={!selected.length || busy} onClick={() => {
        onUse(preview.candidates.filter((_, i) => selected.includes(i)))
        setMessage("Selected facts copied into the profile editor. Review them and press Save profile below to use them for matching.")
      }}>Use selected facts in profile editor</Button>
    </>}
    <p className="text-xs text-muted-foreground">After saving, open a job and choose Analyse fit (or Re-analyse). Qwen through Colibri compares the CV facts with the requirements, showing supporting evidence, gaps and unknowns. Old assessments become outdated. Contact details are unnecessary. Uploaded files and extracted text are not saved; only the profile facts you save persist.</p>
  </div>
}
