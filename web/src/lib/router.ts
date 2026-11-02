import { useEffect, useState } from "react"

export interface Route {
  page: string
  id: number | null
  params: URLSearchParams
}

export function parse(hash: string): Route {
  const [path, query = ""] = hash.replace(/^#\/?/, "").split("?")
  const [page = "today", id] = path.split("/")
  return { page: page || "today", id: id && /^\d+$/.test(id) ? Number(id) : null, params: new URLSearchParams(query) }
}

export function useRoute(): Route {
  const [route, setRoute] = useState(() => parse(window.location.hash))
  useEffect(() => {
    const on = () => setRoute(parse(window.location.hash))
    window.addEventListener("hashchange", on)
    return () => window.removeEventListener("hashchange", on)
  }, [])
  return route
}

export function href(page: string, id?: number | null, params?: Record<string, string>): string {
  const q = params ? new URLSearchParams(Object.entries(params).filter(([, v]) => v)).toString() : ""
  return `#/${page}${id ? `/${id}` : ""}${q ? `?${q}` : ""}`
}

export function go(page: string, id?: number | null, params?: Record<string, string>) {
  window.location.hash = href(page, id, params)
}
