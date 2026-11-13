import { DeliverySettings } from "@/components/delivery-settings"
import { SecuritySettings } from "@/components/security-settings"
import { useEffect, useState } from "react"
import { useStatus } from "@/App"
import { CvImport } from "@/components/cv-import"
import { Facts, PageHeader, Section } from "@/components/common"
import { PlusIcon, XIcon } from "@/components/icons"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { NativeSelect } from "@/components/ui/native-select"
import { Switch } from "@/components/ui/switch"
import { Textarea } from "@/components/ui/textarea"
import { api, useApi } from "@/lib/api"
import { when } from "@/lib/format"

interface Profile { name: string; summary: string; facts: { id: string; text: string }[]; not_claimed: string[] }
interface Prefs { locations: string[]; role_families: string[]; ctc_threshold_lakh: number; reading_interests: string[]; reading_level: string; muted_sources: number[]; muted_terms: string[]; digest: Record<string, number> }
interface ProfileResp { profile: Profile; version: string; preferences: Prefs; families: Record<string, string>; locations: Record<string, string> }
interface SettingsResp {
  model: Record<string, string | number>; limits: Record<string, number>; fetch: Record<string, string | number>; dataDir: string; configFile: string
  schedule: { enabled: boolean; time: string; times: string[]; next_run: string | null; last_result: string | null; last_slot: string | null }
}
interface Suggestion { id: string; text: string }

export default function Settings() {
  const { data, reload } = useApi<ProfileResp>("/api/profile")
  const { data: settings, reload: reloadSettings } = useApi<SettingsResp>("/api/settings")
  const { data: suggestions, reload: reloadSugg } = useApi<Suggestion[]>("/api/feedback/suggestions")
  const { status } = useStatus()
  const [profile, setProfile] = useState<Profile | null>(null)
  const [prefs, setPrefs] = useState<Prefs | null>(null)
  const [saved, setSaved] = useState<string | null>(null)
  useEffect(() => { if (data) { setProfile(data.profile); setPrefs(data.preferences) } }, [data])
  if (!data || !profile || !prefs) return <p className="p-6 text-sm text-muted-foreground">Loading</p>

  const saveProfile = async () => { await api.send("/api/profile", "PUT", profile); setSaved("Profile saved. Fit analyses made with the old profile are now marked outdated."); reload() }
  const savePrefs = async (next: Prefs) => { setPrefs(next); await api.send("/api/preferences", "PUT", next); setSaved("Preferences saved. They apply from the next run."); reloadSugg() }
  const toggle = (list: string[], v: string) => list.includes(v) ? list.filter((x) => x !== v) : [...list, v]
  const apply = async (id: string) => { await api.send(`/api/feedback/suggestions/${id}`, "POST"); reload(); reloadSugg(); setSaved("Preference changed. The model was not retrained; only the rules that rank items changed.") }

  return (
    <div className="flex flex-col gap-8 p-4 sm:p-6">
      <PageHeader title="Profile and settings" line={<>Stored on this computer in {settings?.dataDir ?? "the data folder"}, never in the code repository.</>} />
      {saved && <p role="status" className="text-sm text-(--success-text)">{saved}</p>}

      <DeliverySettings />
      <Section title="Your profile">
        <CvImport onUse={(facts) => setProfile({ ...profile, facts: facts.map((text, i) => ({ id: `P${i + 1}`, text })) })} />
        <p className="max-w-[75ch] text-sm text-muted-foreground">Fit analysis may only cite these facts. Keep them factual: no skill levels or years you can't support.</p>
        <ol className="flex max-w-3xl flex-col gap-2">
          {profile.facts.map((f, i) => (
            <li key={i} className="flex items-start gap-2">
              <span className="w-8 pt-2 text-sm text-muted-foreground">P{i + 1}</span>
              <Textarea aria-label={`Fact ${i + 1}`} maxLength={400} rows={1} className="min-h-9" value={f.text} onChange={(e) => setProfile({ ...profile, facts: profile.facts.map((x, j) => j === i ? { ...x, text: e.target.value } : x) })} />
              <Button size="icon-sm" variant="ghost" aria-label={`Remove fact ${i + 1}`} onClick={() => setProfile({ ...profile, facts: profile.facts.filter((_, j) => j !== i) })}><XIcon className="size-4" /></Button>
            </li>))}
        </ol>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="outline" onClick={() => setProfile({ ...profile, facts: [...profile.facts, { id: "", text: "" }] })}><PlusIcon className="size-4" />Add a fact</Button>
        </div>
        <div className="flex max-w-3xl flex-col gap-1"><Label htmlFor="not-claimed">Things you do not claim (one per line)</Label>
          <Textarea id="not-claimed" rows={3} value={profile.not_claimed.join("\n")} onChange={(e) => setProfile({ ...profile, not_claimed: e.target.value.split("\n") })} /></div>
        <Button className="w-fit" onClick={saveProfile}>Save profile</Button>
      </Section>

      <Section title="Job preferences">
        <fieldset className="flex flex-col gap-2"><legend className="mb-1 text-sm font-medium">Locations that count as a match</legend>
          {Object.entries(data.locations).filter(([k]) => ["bengaluru", "remote_india", "remote_unclear", "india_unspecified"].includes(k)).map(([k, label]) => (
            <label key={k} className="flex items-center gap-2 text-sm"><Checkbox checked={prefs.locations.includes(k)} onCheckedChange={() => savePrefs({ ...prefs, locations: toggle(prefs.locations, k) })} />{label}</label>))}
        </fieldset>
        <fieldset className="flex flex-col gap-2"><legend className="mb-1 text-sm font-medium">Role families</legend>
          {Object.entries(data.families).map(([k, label]) => (
            <label key={k} className="flex items-center gap-2 text-sm"><Checkbox checked={prefs.role_families.includes(k)} onCheckedChange={() => savePrefs({ ...prefs, role_families: toggle(prefs.role_families, k) })} />{label}</label>))}
          <p className="text-xs text-muted-foreground">Other roles go to To review or Outside preferences. Nothing is deleted.</p>
        </fieldset>
        <div className="flex w-64 flex-col gap-1"><Label htmlFor="ctc">Preferred annual CTC, ₹ lakh</Label>
          <Input id="ctc" type="number" min={0} step={1} value={prefs.ctc_threshold_lakh} onChange={(e) => setPrefs({ ...prefs, ctc_threshold_lakh: Number(e.target.value) })} onBlur={() => savePrefs(prefs)} />
          <span className="text-xs text-muted-foreground">A preference for ranking. Listings without pay are kept.</span></div>
        <div className="flex max-w-xl flex-col gap-1"><Label htmlFor="muted">Words that lower an item in briefings (comma separated)</Label>
          <Input id="muted" value={prefs.muted_terms.join(", ")} onChange={(e) => setPrefs({ ...prefs, muted_terms: e.target.value.split(",").map((s) => s.trim()).filter(Boolean) })} onBlur={() => savePrefs(prefs)} /></div>
      </Section>

      <Section title="Reading preferences">
        <div className="flex max-w-xl flex-col gap-1"><Label htmlFor="interests">Interests used to explain why an article matters</Label>
          <Input id="interests" value={prefs.reading_interests.join(", ")} onChange={(e) => setPrefs({ ...prefs, reading_interests: e.target.value.split(",").map((s) => s.trim()).filter(Boolean) })} onBlur={() => savePrefs(prefs)} /></div>
        <div className="flex w-72 flex-col gap-1"><Label htmlFor="level">Technical level</Label>
          <NativeSelect id="level" value={prefs.reading_level} onChange={(e) => savePrefs({ ...prefs, reading_level: e.target.value })}>
            <option value="any">Any</option><option value="prefer_less_technical">Rank sources I marked too technical lower</option></NativeSelect></div>
      </Section>

      <Section title="Suggestions from your feedback">
        {suggestions?.length ? (
          <ul className="flex flex-col gap-3">{suggestions.map((s) => (
            <li key={s.id} className="flex flex-wrap items-center gap-3"><span className="max-w-[70ch] text-sm">{s.text}</span><Button size="sm" variant="outline" onClick={() => apply(s.id)}>Apply</Button></li>))}</ul>
        ) : <p className="text-sm text-muted-foreground">None yet. Repeated feedback suggests a change here. Nothing changes until you apply it.</p>}
      </Section>

      {settings && <ScheduleSection settings={settings} onSaved={reloadSettings} />}

      <SecuritySettings />

      {settings && (
        <Section title="Local model">
          <Facts rows={[
            ["Server", String(settings.model.base_url)],
            ["Configured model", String(settings.model.model_id)],
            ["Serving now", status?.model.reachable ? (status.model.served.join(", ") || "nothing") : "not reachable"],
            ["Context window", `${settings.model.context_tokens} tokens (a token is about 4 characters), up to ${settings.model.max_output_tokens} for the reply`],
            ["Text per request", `about ${settings.model.prompt_char_budget} characters`],
            ["Attempts per item", String(settings.model.max_attempts)],
            ["Requests at once", String(settings.model.concurrency)],
            ["Larger model for unclear cases", settings.model.escalation_model_id ? `${settings.model.escalation_model_id}: ${settings.model.escalation_ready ? "ready" : settings.model.escalation_message}` : "Not configured"],
            ["Paid AI APIs", "None. Cloud sync is a separate optional service."],
          ]} />
          <p className="max-w-[75ch] text-sm text-muted-foreground">Change these in {settings.configFile} and restart SignalDesk. To try the installed 9B model, see "Comparing models" in the README: it runs separately and does not switch this app's model.</p>
        </Section>
      )}
    </div>
  )
}

function ScheduleSection({ settings, onSaved }: { settings: SettingsResp; onSaved: () => void }) {
  const [time, setTime] = useState((settings.schedule.times ?? [settings.schedule.time]).join(", "))
  const [error, setError] = useState<string | null>(null)
  const save = async (enabled: boolean, at = time) => {
    try { await api.send("/api/schedule", "PUT", { enabled, time: at }); setError(null); onSaved() } catch (e) { setError(e instanceof Error ? e.message : String(e)) }
  }
  const s = settings.schedule
  return (
    <Section title="Schedule">
      <p className="max-w-[75ch] text-sm text-muted-foreground">Sweeps at these times (Asia/Kolkata) while SignalDesk is open. A missed sweep runs once at the next start. To sweep while the app is closed, install the Windows task: see docs/V3_SETUP.md. Either way the PC must be on.</p>
      <div className="flex flex-wrap items-end gap-4">
        <label className="flex items-center gap-2 text-sm"><Switch checked={s.enabled} onCheckedChange={(v) => save(!!v)} />Run on schedule</label>
        <div className="flex w-56 flex-col gap-1"><Label htmlFor="time">Times, 24-hour</Label><Input id="time" value={time} onChange={(e) => setTime(e.target.value)} onBlur={() => save(s.enabled, time)} /></div>
      </div>
      {error && <p role="alert" className="text-sm text-(--destructive-text)">{error}</p>}
      <Facts rows={[["Next run", s.enabled && s.next_run ? when(s.next_run) : "Off"], ["Last scheduled run", s.last_result ?? "None"]]} />
    </Section>
  )
}
