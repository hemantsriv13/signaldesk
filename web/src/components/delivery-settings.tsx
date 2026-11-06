import { useState } from "react"
import { Button } from "@/components/ui/button"
import { api, useApi } from "@/lib/api"
interface DeliveryStatus { cloud_configured: boolean; whatsapp_configured: boolean; last_run: { at: string; state: string; message?: string } | null; recent: ({ local_id: number; cloud?: string; whatsapp?: string } | null)[] }
export function DeliverySettings() {
  const { data, reload } = useApi<DeliveryStatus>("/api/delivery", 15000)
  const [message, setMessage] = useState("")
  const [busy, setBusy] = useState(false)
  return <section className="rounded-2xl border bg-card p-5"><p className="text-xs font-semibold uppercase tracking-widest text-primary">Take your desk with you</p><h2 className="my-2 font-heading text-2xl">Cloud reader & WhatsApp</h2><p className="max-w-3xl text-sm text-muted-foreground">Read briefings on your phone with this laptop off, and get new ones on WhatsApp.</p>
    <dl className="my-4 grid gap-2 text-sm"><div>Cloud: <strong>{data?.cloud_configured ? "Configured" : "Setup needed"}</strong></div><div>WhatsApp: <strong>{data?.whatsapp_configured ? "Configured for new briefings" : "Setup needed or disabled"}</strong></div><div>Last checked: {data?.last_run ? `${data.last_run.state} · ${new Date(data.last_run.at).toLocaleString()}` : "Not checked"}</div></dl>
    {data?.last_run?.message && <p className="my-3 text-sm">{data.last_run.message}</p>}
    <Button disabled={busy || !data?.cloud_configured} variant="outline" onClick={async () => { setBusy(true); setMessage(""); try { await api.send("/api/delivery/sync", "POST"); setMessage("Check finished. See the status above."); reload() } catch { setMessage("The check failed. Review the setup and network connection.") } finally { setBusy(false) } }}>{busy ? "Working…" : data?.whatsapp_configured ? "Upload and send new briefings" : "Upload new briefings"}</Button>
    {message && <p role="status" className="my-3 text-sm">{message}</p>}
    {data?.recent.some(Boolean) && <ul className="my-4 space-y-2 text-xs text-muted-foreground">{data.recent.filter((x) => x !== null).map((x) => <li key={x!.local_id}>Briefing {x!.local_id}: cloud {x!.cloud ?? "pending"}; WhatsApp {x!.whatsapp ?? "not submitted"}{x!.whatsapp === "rejected" && <Button variant="ghost" disabled={busy} onClick={async () => { setBusy(true); try { await api.send(`/api/delivery/retry/${x!.local_id}`, "POST"); setMessage("Retry submitted for checking. Review the resulting status."); reload() } catch (e) { setMessage(e instanceof Error ? e.message : String(e)) } finally { setBusy(false) } }}>Retry rejected submission</Button>}</li>)}</ul>}
    <p className="mt-4 text-xs text-muted-foreground">A sent message isn't confirmed as received. These services may charge fees.</p>
  </section>
}
