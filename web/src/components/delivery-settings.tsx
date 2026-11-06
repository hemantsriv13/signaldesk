import { useState } from "react"
import { Button } from "@/components/ui/button"
import { api, useApi } from "@/lib/api"
interface DeliveryStatus { cloud_configured: boolean; last_run: { at: string; state: string; message?: string } | null }
export function DeliverySettings() {
  const { data, reload } = useApi<DeliveryStatus>("/api/delivery", 15000)
  const [message, setMessage] = useState("")
  const [busy, setBusy] = useState(false)
  return <section className="rounded-2xl border bg-card p-5"><p className="text-xs font-semibold uppercase tracking-widest text-primary">Take your desk with you</p><h2 className="my-2 font-heading text-2xl">Phone reader</h2><p className="max-w-3xl text-sm text-muted-foreground">Read finished briefings on your phone with this laptop off.</p>
    <dl className="my-4 grid gap-2 text-sm"><div>Cloud: <strong>{data?.cloud_configured ? "Connected" : "Setup needed"}</strong></div><div>Last checked: {data?.last_run ? `${data.last_run.state} · ${new Date(data.last_run.at).toLocaleString()}` : "Not checked"}</div></dl>
    {data?.last_run?.message && <p className="my-3 text-sm">{data.last_run.message}</p>}
    <Button disabled={busy || !data?.cloud_configured} variant="outline" onClick={async () => { setBusy(true); setMessage(""); try { await api.send("/api/delivery/sync", "POST"); setMessage("Check finished. See the status above."); reload() } catch { setMessage("The check failed. Review the setup and network connection.") } finally { setBusy(false) } }}>{busy ? "Working…" : "Upload new briefings"}</Button>
    {message && <p role="status" className="my-3 text-sm">{message}</p>}
  </section>
}
