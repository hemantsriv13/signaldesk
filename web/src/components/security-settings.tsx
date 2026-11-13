import { useState, type ReactNode } from "react"
import { Facts, Pill, Section } from "@/components/common"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { api, useApi } from "@/lib/api"
import { when } from "@/lib/format"

interface SessionRow { id: number; created_at: string; last_seen_at: string; expires_at: string; ip: string | null; user_agent: string | null; current: boolean }
interface TokenRow { id: number; label: string; hint: string; created_at: string; expires_at: string; last_used_at: string | null; revoked_at: string | null }

/** Signed-in devices and side-panel pairings. Revoking a panel token stops imports at once; the app keeps working. */
export function SecuritySettings() {
  const { data: sessions, reload: reloadSessions } = useApi<{ sessions: SessionRow[] }>("/api/auth/sessions")
  const { data: tokens, reload: reloadTokens } = useApi<{ tokens: TokenRow[] }>("/api/panel/tokens")
  const [label, setLabel] = useState("Edge side panel")
  const [fresh, setFresh] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const pair = async () => {
    const r = await api.send<{ token: string }>("/api/panel/tokens", "POST", { label })
    setFresh(r.token); reloadTokens()
  }
  const revoke = async (id: number) => { await api.send(`/api/panel/tokens/${id}`, "DELETE"); setMessage("Side panel access revoked."); reloadTokens() }
  const signOutOthers = async () => {
    const r = await api.send<{ revoked: number }>("/api/auth/sessions/revoke", "POST", {})
    setMessage(`Signed out ${r.revoked} other session(s).`); reloadSessions()
  }
  const signOut = async () => { await api.send("/api/auth/logout", "POST"); window.location.reload() }
  const signedIn = sessions?.sessions.some((s) => s.current)
  return (
    <Section title="Security">
      {message && <p role="status" className="text-sm text-muted-foreground">{message}</p>}
      <div className="flex flex-col gap-2">
        <p className="text-sm font-medium">Signed-in devices (HTTPS entry point)</p>
        {sessions?.sessions.length ? (
          <ul className="flex flex-col gap-1 text-sm">{sessions.sessions.map((s) => (
            <li key={s.id}>{s.current && <Pill tone="success">This device</Pill>} {s.user_agent?.slice(0, 60) || "Unknown browser"} · {s.ip} · last active {when(s.last_seen_at)}</li>))}</ul>
        ) : <p className="text-sm text-muted-foreground">None. This PC's own address does not need sign-in.</p>}
        <div className="flex flex-wrap gap-2">
          {!!sessions?.sessions.length && <Button size="sm" variant="outline" onClick={signOutOthers}>Sign out other devices</Button>}
          {signedIn && <Button size="sm" variant="ghost" onClick={signOut}>Sign out</Button>}
        </div>
      </div>
      <div className="flex flex-col gap-2">
        <p className="text-sm font-medium">Edge side panel</p>
        <p className="max-w-[75ch] text-sm text-muted-foreground">A pairing token lets the panel import and compare jobs only. It cannot open settings, contacts, outreach, exports or runs.</p>
        <div className="flex flex-wrap items-end gap-2">
          <div className="flex w-64 flex-col gap-1"><Label htmlFor="tok-label">Name</Label><Input id="tok-label" value={label} onChange={(e) => setLabel(e.target.value)} /></div>
          <Button variant="outline" onClick={pair}>Create pairing token</Button>
        </div>
        {fresh && (
          <div role="status" className="flex flex-col gap-1 rounded-lg bg-muted p-3 text-sm">
            <p>Paste this into the side panel now. It is shown only once.</p>
            <code className="break-all select-all">{fresh}</code>
            <Button size="sm" variant="ghost" className="w-fit" onClick={() => setFresh(null)}>Done, hide it</Button>
          </div>
        )}
        {tokens?.tokens.length ? (
          <Facts rows={tokens.tokens.map((t): [string, ReactNode] => [`${t.label} (…${t.hint})`, t.revoked_at ? `Revoked ${when(t.revoked_at)}` : (
            <span className="flex flex-wrap items-center gap-2">Last used {t.last_used_at ? when(t.last_used_at) : "never"} · expires {when(t.expires_at)}
              <Button size="sm" variant="ghost" onClick={() => revoke(t.id)}>Revoke</Button></span>)])} />
        ) : <p className="text-sm text-muted-foreground">No side panel paired.</p>}
      </div>
    </Section>
  )
}
