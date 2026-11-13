// SignalDesk side panel. Reads only what you paste. It never reads web pages, tabs, cookies,
// history or the clipboard, and never fetches a pasted link. All text is shown with textContent.
"use strict"

const $ = (id) => document.getElementById(id)
let conn = null           // { endpoint, token } from chrome.storage.local, never synced
let lastIds = []
let poll = null

// ---------------------------------------------------------------- views and banner
function show(view) {
  for (const v of ["connect", "compare", "searches"]) $(`view-${v}`).hidden = v !== view
  for (const btn of document.querySelectorAll("nav button")) {
    if (btn.dataset.view === view) btn.setAttribute("aria-current", "page")
    else btn.removeAttribute("aria-current")
  }
  if (needsConnection(view)) return
  if (view === "searches") loadMetrics()
  if (view === "compare") loadLabels()
}
function needsConnection(view) { return view !== "connect" && !conn ? (show("connect"), true) : false }
function banner(text) { $("banner").hidden = !text; $("banner-text").textContent = text || "" }

// ---------------------------------------------------------------- connection
function originOf(endpoint) {
  const u = new URL(endpoint)
  const local = u.protocol === "http:" && (u.hostname === "127.0.0.1" || u.hostname === "localhost")
  if (u.protocol !== "https:" && !local) throw new Error("Use https:// for another device, or http://127.0.0.1 on this PC.")
  return `${u.protocol}//${u.hostname}`
}

async function api(path, method = "GET", body) {
  if (!conn) { show("connect"); throw new Error("Not connected") }
  let r
  try {
    r = await fetch(conn.endpoint.replace(/\/$/, "") + path, {
      method, credentials: "omit", cache: "no-store",
      headers: { authorization: `Bearer ${conn.token}`, ...(body ? { "content-type": "application/json" } : {}) },
      body: body ? JSON.stringify(body) : undefined,
    })
  } catch {
    banner("SignalDesk is not reachable. Check that it is running, then reconnect.")
    throw new Error("unreachable")
  }
  if (r.status === 401 || r.status === 403) {
    const detail = (await r.json().catch(() => ({}))).detail
    banner(detail || "Access was revoked or has expired. Pair the panel again.")
    throw new Error("unauthorised")
  }
  const data = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(data.detail || `HTTP ${r.status}`)
  banner("")
  return data
}

$("connect").addEventListener("click", async () => {
  const endpoint = $("endpoint").value.trim(), token = $("token").value.trim()
  const status = $("connect-status")
  try {
    const origin = originOf(endpoint)
    // Ask for access to this one SignalDesk address only, at the moment you connect.
    const granted = await chrome.permissions.request({ origins: [`${origin}/*`] })
    if (!granted) { status.textContent = "Permission to reach SignalDesk was not granted."; return }
    conn = { endpoint, token }
    await api("/api/panel/ping")
    await chrome.storage.local.set({ conn })
    $("token").value = ""
    status.textContent = "Connected."
    show("compare")
  } catch (e) {
    if (e.message !== "unreachable" && e.message !== "unauthorised") status.textContent = e.message
    conn = null
  }
})

$("disconnect").addEventListener("click", async () => {
  if (conn) {
    try { await chrome.permissions.remove({ origins: [`${originOf(conn.endpoint)}/*`] }) } catch { /* already removed */ }
  }
  conn = null
  await chrome.storage.local.remove("conn")
  $("connect-status").textContent = "Disconnected. Also revoke the token in SignalDesk settings."
  banner("")
})
$("reconnect").addEventListener("click", () => { banner(""); show("connect") })
for (const btn of document.querySelectorAll("nav button")) btn.addEventListener("click", () => show(btn.dataset.view))

// ---------------------------------------------------------------- labels
async function loadLabels() {
  try {
    const { labels } = await api("/api/panel/labels")
    const list = $("labels")
    list.replaceChildren(...labels.map((l) => Object.assign(document.createElement("option"), { value: l })))
    if (!$("label").value && labels[0]) $("label").value = labels[0]
  } catch { /* banner already shown */ }
}

// ---------------------------------------------------------------- preview
function el(tag, props = {}, ...children) {
  const n = Object.assign(document.createElement(tag), props)
  for (const c of children) if (c !== null && c !== undefined) n.append(c)
  return n
}
function field(labelText, value, multiline = false) {
  const id = `f${Math.random().toString(36).slice(2)}`
  const input = multiline ? el("textarea", { id, rows: 3, value }) : el("input", { id, value })
  return [el("label", { htmlFor: id, textContent: labelText }), input]
}

$("parse").addEventListener("click", async () => {
  try {
    const { listings, notes } = await api("/api/panel/parse", "POST", { text: $("paste").value })
    $("parse-notes").textContent = listings.length ? `${listings.length} listing(s) found. Check them, then save.` + (notes.length ? ` ${notes.join(" ")}` : "")
      : "No listings found. Put a line with --- between listings, or include title, company and location lines."
    $("preview").replaceChildren(...listings.map(previewCard))
    $("save").hidden = !listings.length
  } catch (e) { $("parse-notes").textContent = e.message }
})

function previewCard(l) {
  const [tL, tI] = field("Title", l.title), [cL, cI] = field("Company", l.company), [lL, lI] = field("Location", l.location)
  const [uL, uI] = field("Link (kept as the source; not opened or fetched)", l.url || ""), [dL, dI] = field("Description", l.description || "", true)
  const remove = el("button", { type: "button", textContent: "Remove" })
  const card = el("li", { className: "card" }, tL, tI, cL, cI, lL, lI, uL, uI, dL, dI,
    el("p", { className: "muted", textContent: l.thin ? "Card only: SignalDesk will ask for the full description before judging fit." : "" }), remove)
  card.read = () => ({ title: tI.value.trim(), company: cI.value.trim(), location: lI.value.trim(), url: uI.value.trim(), description: dI.value.trim() })
  remove.addEventListener("click", () => { card.remove(); $("save").hidden = !$("preview").children.length })
  return card
}

$("save").addEventListener("click", async () => {
  const label = $("label").value.trim()
  if (!label) { $("parse-notes").textContent = "Name the search you used first."; $("label").focus(); return }
  const listings = [...$("preview").children].map((c) => c.read()).filter((l) => l.title && l.company)
  try {
    const { results } = await api("/api/panel/import", "POST", { label, listings })
    $("preview").replaceChildren(); $("save").hidden = true; $("paste").value = ""
    $("parse-notes").textContent = `Saved under "${label}".`
    renderResults(results)
    loadLabels()
  } catch (e) { $("parse-notes").textContent = e.message }
})

// ---------------------------------------------------------------- results
const STATE = {
  assessed: ["Assessed", "good"], queued: ["Analysis queued", ""], queued_model_offline: ["Queued: Colibri is offline", "warn"],
  need_full_description: ["Need full description", "warn"], location_not_eligible: ["Location not eligible", "bad"], not_assessed: ["Not assessed", ""],
}

function renderResults(results) {
  lastIds = results.map((r) => r.id)
  $("results-title").hidden = !results.length
  $("results").replaceChildren(...results.map(resultCard))
  clearInterval(poll)
  if (results.some((r) => r.state.startsWith("queued"))) {
    let rounds = 0
    poll = setInterval(async () => {
      if (++rounds > 24) return clearInterval(poll)
      try {
        const { results: fresh } = await api(`/api/panel/results?ids=${lastIds.join(",")}`)
        $("results").replaceChildren(...fresh.map(resultCard))
        if (!fresh.some((r) => r.state.startsWith("queued"))) clearInterval(poll)
      } catch { clearInterval(poll) }
    }, 5000)
  }
}

function resultCard(r) {
  const [label, tone] = STATE[r.state] || [r.state, ""]
  const tags = el("div", { className: "row" },
    el("span", { className: `tag ${r.eligible ? "good" : "bad"}`, textContent: r.location_label }),
    el("span", { className: "tag", textContent: r.families.join(" + ") }),
    el("span", { className: `tag ${tone}`, textContent: label }),
    r.match ? el("span", { className: "tag", textContent: `Model: ${r.match}` }) : null,
    r.manual_import ? el("span", { className: "tag", textContent: "Manual import" }) : el("span", { className: "tag good", textContent: "On employer's board" }),
    r.decision ? el("span", { className: "tag good", textContent: `You: ${r.decision}` }) : null)
  const card = el("li", { className: "card" },
    el("strong", { textContent: r.title }), el("span", { className: "muted", textContent: `${r.company} · ${r.location || "location not stated"}` }), tags,
    r.phrase ? el("p", { className: "quote", textContent: `“${r.phrase}”` }) : null,
    r.background ? el("p", { textContent: `Your background: ${r.background}` }) : null,
    r.gap ? el("p", { className: "muted", textContent: `Gap or unknown: ${r.gap}` }) : null)
  const actions = el("div", { className: "row" })
  const decide = (d) => async () => { try { card.replaceWith(resultCard(await api(`/api/panel/jobs/${r.id}/decision`, "POST", { decision: d }))) } catch (e) { alertInline(card, e) } }
  actions.append(el("button", { type: "button", textContent: r.decision === "shortlisted" ? "Shortlisted" : "Shortlist", onclick: decide("shortlist") }),
    el("button", { type: "button", textContent: r.decision === "dismissed" ? "Dismissed" : "Dismiss", onclick: decide("dismiss") }))
  if (r.original_url && /^https?:\/\//.test(r.original_url)) {
    actions.append(el("a", { href: r.original_url, target: "_blank", rel: "noopener noreferrer", textContent: "Open original" }))
  }
  card.append(actions)
  if (r.state === "need_full_description" && r.manual_import) {
    const [dL, dI] = field("Paste the full description", "", true)
    const add = el("button", { type: "button", textContent: "Refresh with description" })
    add.addEventListener("click", async () => {
      try { card.replaceWith(resultCard(await api(`/api/panel/jobs/${r.id}/description`, "POST", { description: dI.value }))) } catch (e) { alertInline(card, e) }
    })
    card.append(dL, dI, add)
  }
  return card
}
function alertInline(card, e) { card.append(el("p", { className: "muted", role: "alert", textContent: e.message })) }

// ---------------------------------------------------------------- searches
function rate(n, d) { return d ? `${n} of ${d} (${Math.round((n / d) * 100)}%)` : `${n} of 0` }
async function loadMetrics() {
  try {
    const m = await api("/api/panel/metrics")
    $("metrics-note").textContent = m.note
    const head = el("tr", {}, ...["Search", "Reviewed", "Eligible location", "Enough to assess", "You shortlisted", "You applied", "Model: potential match"].map((t) => el("th", { textContent: t })))
    const row = (name, x) => el("tr", {},
      el("td", { textContent: name + (x.small_sample ? " (small sample)" : "") }), el("td", { className: "num", textContent: String(x.reviewed) }),
      el("td", { className: "num", textContent: rate(x.eligible, x.reviewed) }), el("td", { className: "num", textContent: rate(x.assessable, x.eligible) }),
      el("td", { className: "num", textContent: rate(x.shortlisted, x.eligible) }), el("td", { className: "num", textContent: rate(x.applied, x.shortlisted) }),
      el("td", { className: "num", textContent: rate(x.model_potential, x.assessable) }))
    const table = el("table", {}, el("thead", {}, head), el("tbody", {}, ...m.labels.map((x) => row(x.label, x)), row("All searches (each job once)", m.overall)))
    $("metrics").replaceChildren(table, el("p", { className: "muted", textContent: "Shortlisted and applied are your decisions. The last column is the local model's prediction." }))
  } catch { /* banner already shown */ }
}

// ---------------------------------------------------------------- start
chrome.storage.local.get("conn").then(({ conn: saved }) => {
  conn = saved || null
  if (conn) $("endpoint").value = conn.endpoint
  show(conn ? "compare" : "connect")
})
