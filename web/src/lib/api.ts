import { useCallback, useEffect, useRef, useState } from "react"

export class ApiError extends Error {}

async function handle<T>(r: Response): Promise<T> {
  if (!r.ok) {
    let msg = `Request failed (HTTP ${r.status})`
    try {
      const body = await r.json()
      if (typeof body.detail === "string") msg = body.detail
    } catch { /* keep the generic message */ }
    throw new ApiError(msg)
  }
  return r.json() as Promise<T>
}

export const api = {
  get: <T,>(path: string) => fetch(path).then((r) => handle<T>(r)),
  send: <T,>(path: string, method: "POST" | "PUT" | "PATCH" | "DELETE", body?: unknown) =>
    fetch(path, { method, headers: { "content-type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body) }).then((r) => handle<T>(r)),
}

/** Load `path`, and reload every `everyMs` while the page is visible (0 = no polling). */
export function useApi<T>(path: string | null, everyMs = 0) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const current = useRef(path)
  current.current = path

  const reload = useCallback(async () => {
    if (!path) return
    setLoading(true)
    try {
      const d = await api.get<T>(path)
      if (current.current === path) {
        setData(d)
        setError(null)
      }
    } catch (e) {
      if (current.current === path) setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [path])

  useEffect(() => {
    setData(null)
    reload()
    if (!everyMs) return
    const id = window.setInterval(() => document.visibilityState === "visible" && reload(), everyMs)
    return () => window.clearInterval(id)
  }, [reload, everyMs])

  return { data, error, loading, reload, setData }
}

// ---------------------------------------------------------------- shapes returned by the API
export type Tone = "neutral" | "warning" | "danger" | "success"
export interface DigestItem {
  type: "job" | "article" | "case"
  id: number
  title: string
  subtitle: string
  summary: string | null
  match?: string | null
  why: string[]
  badges: { tone: Tone; text: string }[]
  detail: string
  original_url: string
}
export interface Digest {
  id: number
  created_at?: string
  generated_at: string
  status?: string
  jobs: DigestItem[]
  articles: DigestItem[]
  case: DigestItem | null
  term: { term: string; explanation: string; from_title: string; detail: string; original_url: string } | null
  action: { action: string; ref: string; by: "model" | "rule"; model_id?: string; reason?: string } | null
  refs: Record<string, string>
  notes: string[]
  quiet: boolean
  model_id: string
}
export interface ModelState {
  reachable: boolean
  ready: boolean
  served: string[]
  configured: string
  message: string
  contextTokens?: number
}
export interface ActiveRun {
  id: number
  agent: string
  agentName: string
  status: string
  started_at: string
  tasks: Record<string, number>
  stats: Record<string, number>
}
export interface Status {
  model: ModelState
  runs: ActiveRun[]
  queue: { queued: number; running: number; failed: number }
  counts: Record<string, number>
  failures: { type: string; id: number; name: string; error: string; at: string }[]
  latestDigest: Digest | null
  schedule: { enabled: boolean; time: string; next_run: string | null; last_result: string | null; timezone: string }
}
export interface JobRow {
  id: number
  employer: string
  title: string
  location_raw: string | null
  location_class: string
  salary_text: string | null
  bucket: string
  bucket_reason: string
  status: string
  change_state: string
  listing_state: string
  published_at: string | null
  first_seen_at: string
  last_verified_at: string | null
  verified_hours_ago: number | null
  source: string
  match: string | null
  analysis_pending: boolean
  injection_flag: number
}
export interface Analysis<T> {
  id: number
  output: T
  validation: { notes: string[] }
  inputs: {
    coverage?: { chars_sent: number; chars_total: number; complete: boolean; profile_fact_ids?: string[]; profile_facts_total?: number }
    facts_sent?: { id: string; text: string }[]
    [k: string]: unknown
  }
  model_id: string
  prompt_version: string
  created_at: string
  outdated: boolean
}
export interface TaskRef { id: number; status: string; attempts: number; error: string | null; note: string | null }
export interface Quote { req?: string; point?: string; quote: string; quote_found: boolean }
export interface JobFit {
  essential: Quote[]
  preferred: Quote[]
  evidence: { req: string; facts: string[]; note: string }[]
  gaps: string[]
  unknowns: string[]
  match: string
  summary: string
  injection_seen: boolean
}
export interface ArticleRow {
  id: number
  title: string
  source_name: string | null
  source_kind: string | null
  author: string | null
  published_at: string | null
  retrieved_at: string
  content_basis: "full" | "excerpt" | "metadata"
  url: string
  origin: string
  case_candidate: number
  injection_flag: number
  repeats: number
  has_card: boolean
  case_suitability: string | null
  card_pending: boolean
  case_pending: boolean
  feedback: string[]
}
export interface Card {
  main_argument: string
  evidence: Quote[]
  why_it_matters: string
  limitations: string
  concept: { term: string; explanation: string }
  kind: string
  injection_seen: boolean
}
export interface CaseField { text: string; label: "source_fact" | "vendor_claim" | "inference" | "missing"; quote: string | null }
export type CaseStudy = Record<string, CaseField> & { suitability: string; suitability_reason: string; injection_seen: boolean }
