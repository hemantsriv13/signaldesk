const IST = "Asia/Kolkata"

export function when(iso: string | null | undefined): string {
  if (!iso) return "unknown"
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString("en-IN", { timeZone: IST, day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })
}

export function day(iso: string | null | undefined): string {
  if (!iso) return "unknown"
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleDateString("en-IN", { timeZone: IST, day: "numeric", month: "short", year: "numeric" })
}

export function ago(iso: string | null | undefined): string {
  if (!iso) return "never"
  const ms = Date.now() - new Date(iso).getTime()
  const m = Math.round(ms / 60000)
  if (m < 1) return "just now"
  if (m < 60) return `${m} min ago`
  const h = Math.round(m / 60)
  if (h < 48) return `${h} h ago`
  return `${Math.round(h / 24)} days ago`
}

export const plural = (n: number, one: string, many = `${one}s`) => `${n.toLocaleString("en-IN")} ${n === 1 ? one : many}`

export const AGENT_PAGE: Record<string, string> = {
  funding_scout: "hiring",
  job_scout: "jobs",
  reading_scout: "reading",
  case_analyst: "cases",
  contact_scout: "outreach",
  digest_editor: "saved",
  source_refresh: "sources",
}

const ROUNDS: Record<string, string> = { pre_seed: "Pre-seed", seed: "Seed", angel: "Angel", bridge: "Bridge", growth: "Growth", venture_debt: "Venture debt", debt: "Debt", unknown: "Round not stated" }
export function ROUND_LABEL(r: string): string {
  const m = r.match(/^(pre_)?series_([a-h])$/)
  return m ? `${m[1] ? "Pre-" : ""}Series ${m[2].toUpperCase()}` : ROUNDS[r] ?? r
}

export const SOURCE_LABEL: Record<string, string> = {
  greenhouse: "Greenhouse", lever: "Lever", ashby: "Ashby", wellfound: "Wellfound", yc_jobs: "YC jobs", manual: "Added by you",
}
