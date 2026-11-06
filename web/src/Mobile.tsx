import { useEffect, useMemo, useState } from "react"
import { createClient, type Session } from "@supabase/supabase-js"
import { App as NativeApp } from "@capacitor/app"
import { Capacitor } from "@capacitor/core"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

interface Item { type: string; id: number; title: string; subtitle?: string; summary?: string; original_url?: string; match?: string; badges?: { text: string }[] }
interface Brief { id: string; created_at: string; synced_at: string; payload: { generated_at: string; jobs: Item[]; articles: Item[]; case: Item | null; term: { term: string; explanation: string } | null; notes: string[]; model_id?: string } }
interface Connection { url: string; key: string }
const UUID = /^[0-9a-f-]{36}$/i
const safeUrl = (url?: string) => { try { const u = new URL(url ?? ""); return ["https:", "http:"].includes(u.protocol) ? u.href : null } catch { return null } }
const read = (key: string) => { try { return localStorage.getItem(key) } catch { return null } }
const store = (key: string, value: string | null) => { try { if (value === null) localStorage.removeItem(key); else localStorage.setItem(key, value) } catch { /* no persistent device cache */ } }
const incoming = (url: string) => { try { const id = new URL(url).searchParams.get("digest"); return id && UUID.test(id) ? id : null } catch { return null } }

export default function Mobile() {
  const [connection, setConnection] = useState<Connection | null>(() => {
    const url = import.meta.env.VITE_SUPABASE_URL, key = import.meta.env.VITE_SUPABASE_ANON_KEY
    if (url && key) return { url, key }
    try { return JSON.parse(read("signaldesk-connection") ?? "null") } catch { return null }
  })
  if (!connection) return <Connect onSave={(c) => { store("signaldesk-connection", JSON.stringify(c)); setConnection(c) }} />
  return <Reader connection={connection} onDisconnect={() => { store("signaldesk-connection", null); setConnection(null) }} />
}

function Connect({ onSave }: { onSave: (c: Connection) => void }) {
  const [url, setUrl] = useState("")
  const [key, setKey] = useState("")
  const [error, setError] = useState("")
  return <main className="mobile-shell"><div className="mobile-paper"><span className="brand-mark">s</span><p className="mt-5 text-xs font-semibold uppercase tracking-widest text-primary">Your pocket field notes</p><h1 className="my-3 font-heading text-4xl">Welcome to SignalDesk.</h1><p className="mb-6 text-sm text-muted-foreground">Connect your private cloud reader. Use the project's public URL and anon/publishable key. Never enter a service-role key or WhatsApp token here.</p>
    <form className="grid gap-3" onSubmit={(e) => { e.preventDefault(); if (!url.startsWith("https://") || !key.trim()) setError("Enter an HTTPS project URL and its public key."); else if (key.startsWith("sb_secret_") || (() => { try { return JSON.parse(atob(key.split(".")[1])).role === "service_role" } catch { return false } })()) setError("That is a server-only secret key. Use the public anon/publishable key."); else onSave({ url: url.trim(), key: key.trim() }) }}>
      <Label htmlFor="cloud-url">Supabase project URL</Label><Input id="cloud-url" type="url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://your-project.supabase.co" required />
      <Label htmlFor="public-key">Public anon / publishable key</Label><Input id="public-key" value={key} onChange={(e) => setKey(e.target.value)} required /><Button type="submit">Connect my reader</Button>
    </form>{error && <p role="alert">{error}</p>}<p className="mt-5 text-xs text-muted-foreground">Your laptop creates the briefings. This app reads synced copies even when your laptop is off. Account setup is described in docs/V2_SETUP.md.</p></div></main>
}

function Reader({ connection, onDisconnect }: { connection: Connection; onDisconnect: () => void }) {
  const client = useMemo(() => createClient(connection.url, connection.key), [connection])
  const [session, setSession] = useState<Session | null>(null)
  const [ready, setReady] = useState(false)
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)
  const [briefs, setBriefs] = useState<Brief[]>([])
  const [digest, setDigest] = useState<string | null>(() => incoming(window.location.href))
  const [tab, setTab] = useState("Today")
  const [focus, setFocus] = useState<Item | null>(null)
  const [cached, setCached] = useState(false)
  const [saved, setSaved] = useState<string[]>([])
  useEffect(() => {
    client.auth.getSession().then(({ data, error }) => { if (error) setError(error.message); setSession(data.session); setReady(true) }).catch(() => { setError("Could not restore your session. Check the connection."); setReady(true) })
    const { data } = client.auth.onAuthStateChange((_event, s) => setSession(s))
    return () => { data.subscription.unsubscribe() }
  }, [client])
  useEffect(() => {
    if (!Capacitor.isNativePlatform()) return
    let off: (() => void) | undefined
    const receive = (url: string) => { const id = incoming(url); if (id) { setDigest(id); setTab("Today"); setFocus(null) } }
    NativeApp.getLaunchUrl().then((r) => { if (r) receive(r.url) })
    const handle = NativeApp.addListener("appUrlOpen", (event) => receive(event.url))
    handle.then((h) => { off = () => h.remove() })
    return () => { if (off) off(); else handle.then((h) => h.remove()) }
  }, [])
  const load = async (user: Session) => {
    setBusy(true); setError("")
    try {
      // RLS enforces ownership; the client filter also documents the expected scope.
      const r = await client.from("signaldesk_digests").select("*").eq("owner_id", user.user.id).order("created_at", { ascending: false }).limit(50)
      if (r.error) throw r.error
      const next = (r.data ?? []) as Brief[]
      setBriefs(next); setCached(false)
      store("signaldesk-cache:" + user.user.id, JSON.stringify(next))
    } catch { setCached(true); setError("Could not refresh. Showing the last copies saved on this device, if any.") }
    finally { setBusy(false) }
  }
  useEffect(() => {
    setBriefs([]); setFocus(null)
    if (!session) return
    try { setBriefs(JSON.parse(read("signaldesk-cache:" + session.user.id) ?? "[]")); setSaved(JSON.parse(read("signaldesk-saved:" + session.user.id) ?? "[]")); setCached(true) } catch { /* empty cache */ }
    void load(session)
  // Reload on identity changes, not every token refresh.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session?.user.id])
  if (!ready) return <main className="mobile-shell"><p>Opening your desk…</p></main>
  if (!session) return <main className="mobile-shell"><div className="mobile-paper"><span className="brand-mark">s</span><h1 className="my-5 font-heading text-4xl">Your next good find awaits.</h1><p className="mb-5 text-sm">Sign in to the reader account created in your own Supabase project.</p><form className="grid gap-3" onSubmit={async (e) => {
    e.preventDefault(); setBusy(true); setError("")
    try { const r = await client.auth.signInWithPassword({ email, password }); if (r.error) setError(r.error.message) } catch { setError("Sign-in failed. Check your connection and project settings.") } finally { setBusy(false) }
  }}><Label htmlFor="reader-email">Email</Label><Input id="reader-email" type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required /><Label htmlFor="reader-password">Password</Label><Input id="reader-password" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required /><Button type="submit" disabled={busy}>{busy ? "Signing in…" : "Open my desk"}</Button></form>{error && <p role="alert" className="mt-3 text-sm">{error}</p>}<Button variant="ghost" className="mt-3" onClick={onDisconnect}>Change cloud connection</Button></div></main>
  const current = briefs.find((b) => b.id === digest) ?? (digest ? null : briefs[0])
  const all = current ? [...current.payload.jobs, ...current.payload.articles, ...(current.payload.case ? [current.payload.case] : [])] : []
  const bookmark = (item: Item) => {
    const id = item.type + ":" + item.id
    const next = saved.includes(id) ? saved.filter((x) => x !== id) : [...saved, id]
    setSaved(next); store("signaldesk-saved:" + session.user.id, JSON.stringify(next))
  }
  const visible = tab === "Jobs" ? all.filter((i) => i.type === "job") : tab === "Reading" ? all.filter((i) => i.type !== "job") : tab === "Saved" ? briefs.flatMap((b) => [...b.payload.jobs, ...b.payload.articles, ...(b.payload.case ? [b.payload.case] : [])]).filter((i, n, a) => saved.includes(i.type + ":" + i.id) && a.findIndex((x) => x.type === i.type && x.id === i.id) === n) : all
  return <main className="mobile-shell"><header className="mobile-top"><span className="flex items-center gap-2 font-heading text-xl"><span className="brand-mark">s</span>SignalDesk</span><Button variant="ghost" onClick={async () => {
    store("signaldesk-cache:" + session.user.id, null); store("signaldesk-saved:" + session.user.id, null)
    try { await client.auth.signOut({ scope: 'local' }) } finally { setSession(null); setBriefs([]); setSaved([]) }
  }}>Sign out</Button></header><div className="mobile-content">
    <section className="welcome-card rounded-2xl px-5 py-4"><h1 className="font-heading text-xl">Make room for good ideas.</h1></section>
    <div className="my-4 flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground"><span>{cached ? "Saved device copies" : "Cloud copies"}{current ? ` · synced ${new Date(current.synced_at).toLocaleString()}` : ""}</span><Button variant="outline" disabled={busy} onClick={() => load(session)}>{busy ? "Refreshing…" : "Refresh"}</Button></div>
    {error && <p role="status" className="mb-3 text-sm">{error}</p>}
    {digest && !current && <div className="mobile-paper"><p>This briefing is not available in the latest 50 synced copies. It may have been archived or you may be signed in to another account.</p><Button onClick={() => setDigest(null)}>Show latest briefing</Button></div>}
    {briefs.length > 0 && <label className="mb-4 grid gap-2 text-sm">Choose a briefing<select className="rounded-lg border bg-card p-3" value={current?.id ?? ""} onChange={(e) => { setDigest(e.target.value); setFocus(null) }}>{briefs.map((b) => <option key={b.id} value={b.id}>{new Date(b.created_at).toLocaleString()}</option>)}</select></label>}
    {focus ? <article className="mobile-paper"><Button variant="ghost" onClick={() => setFocus(null)}>← Back to briefing</Button><p className="mt-4 text-xs uppercase tracking-widest text-primary">{focus.type === "job" ? "Opportunity" : focus.type === "case" ? "AI in practice" : "A useful read"}</p><h2 className="my-3 font-heading text-3xl">{focus.title}</h2><p className="text-sm text-muted-foreground">{focus.subtitle}</p><p className="my-5 whitespace-pre-wrap leading-relaxed">{focus.summary || "No AI summary was available when this briefing was created. Open the original source."}</p>{focus.match && <p className="text-sm">CV assessment: {focus.match}. Advisory; check the requirements yourself.</p>}{focus.badges?.map((b) => <p key={b.text} className="my-2 text-sm text-muted-foreground">{b.text}</p>)}<p className="my-4 text-xs text-muted-foreground">This is a saved snapshot, not a live check of the listing. AI summaries may contain mistakes.</p><div className="flex flex-wrap gap-3">{safeUrl(focus.original_url) && <a className="rounded-lg bg-primary px-4 py-3 text-sm font-medium text-primary-foreground" href={safeUrl(focus.original_url)!} target="_blank" rel="noreferrer">Open original source ↗</a>}<Button variant="outline" onClick={() => bookmark(focus)}>{saved.includes(focus.type + ":" + focus.id) ? "Remove from saved" : "Save on this device"}</Button></div></article> : <>
      <div className="grid gap-4 sm:grid-cols-2">{visible.map((item) => <button key={item.type + ":" + item.id} className="mobile-item text-left" onClick={() => setFocus(item)}><span className="text-xs font-semibold uppercase tracking-widest text-primary">{item.type === "job" ? "Opportunity" : item.type === "case" ? "AI in practice" : "Reading"}</span><h2 className="my-3 font-heading text-2xl leading-tight">{item.title}</h2><p className="text-xs text-muted-foreground">{item.subtitle}</p><p className="mt-3 line-clamp-3 text-sm leading-relaxed">{item.summary || "Open this find to explore the original source."}</p><span className="mt-4 block text-sm font-medium text-primary">Take a closer look →</span></button>)}</div>
      {!visible.length && <section className="mobile-paper"><h2 className="font-heading text-2xl">A little breathing room.</h2><p className="mt-2 text-sm">{briefs.length ? "No items in this view yet. Try another tab or briefing." : "No briefings synced yet. Start the desktop agents and configure cloud sync to bring your first finds here."}</p></section>}
      {tab === "Today" && current?.payload.term && <aside className="my-5 rounded-2xl bg-[#fae4c7] p-5 text-[#5a3b22]"><p className="text-xs uppercase tracking-widest">One idea to keep</p><h2 className="my-2 font-heading text-2xl">{current.payload.term.term}</h2><p className="text-sm leading-relaxed">{current.payload.term.explanation}</p></aside>}
      {current?.payload.notes.map((n) => <p key={n} className="my-3 text-xs text-muted-foreground">{n}</p>)}
    </>}
    <p className="my-6 text-xs text-muted-foreground">Your laptop makes new briefings.</p>
  </div><nav className="mobile-nav" aria-label="Reader sections">{["Today", "Jobs", "Reading", "Saved"].map((name) => <button key={name} aria-current={tab === name ? "page" : undefined} onClick={() => { setTab(name); setFocus(null) }} className={tab === name ? "active" : ""}>{name}</button>)}</nav></main>
}
