import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { setCsrf } from "@/lib/api"

/** Shown on the HTTPS entry point until you sign in. The password is set on the PC with
 *  .venv\Scripts\python -m signaldesk auth set-password */
export function SignIn({ passwordSet, onDone }: { passwordSet: boolean; onDone: () => void }) {
  const [password, setPassword] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true); setError(null)
    try {
      const r = await fetch("/api/auth/login", { method: "POST", credentials: "same-origin", headers: { "content-type": "application/json" }, body: JSON.stringify({ password }) })
      const body = await r.json()
      if (!r.ok) throw new Error(typeof body.detail === "string" ? body.detail : `Sign-in failed (HTTP ${r.status})`)
      setCsrf(body.csrf); setPassword(""); onDone()
    } catch (err) { setError(err instanceof Error ? err.message : String(err)) } finally { setBusy(false) }
  }
  return (
    <main className="flex min-h-dvh items-center justify-center p-4">
      <form onSubmit={submit} className="flex w-full max-w-sm flex-col gap-4 rounded-xl border border-border bg-card p-6">
        <h1 className="font-heading text-2xl font-medium">Sign in to SignalDesk</h1>
        {passwordSet ? (
          <>
            <div className="flex flex-col gap-1"><Label htmlFor="pw">Password</Label>
              <Input id="pw" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} /></div>
            {error && <p role="alert" className="text-sm text-(--destructive-text)">{error}</p>}
            <Button type="submit" disabled={busy}>{busy ? "Signing in" : "Sign in"}</Button>
          </>
        ) : (
          <p className="text-sm">No password is set yet. On the PC, run <code>.venv\Scripts\python -m signaldesk auth set-password</code>, then reload this page.</p>
        )}
      </form>
    </main>
  )
}
