import { createContext, useContext, useEffect, useState, type ReactNode } from "react"
import {
  BookmarkSimpleIcon, BookOpenIcon, BriefcaseIcon, FlaskIcon, GearIcon, MoonIcon, QuestionIcon, RobotIcon, RssIcon, SunIcon,
} from "@/components/icons"
import { Button } from "@/components/ui/button"
import { Sidebar, SidebarContent, SidebarFooter, SidebarGroup, SidebarHeader, SidebarItem } from "@/components/ui/sidebar"
import { StatusIndicator } from "@/components/ui/status-indicator"
import { useApi, type Status } from "@/lib/api"
import { go, useRoute } from "@/lib/router"
import Cases from "@/pages/Cases"
import How from "@/pages/How"
import Jobs from "@/pages/Jobs"
import Reading from "@/pages/Reading"
import Runs from "@/pages/Runs"
import Saved from "@/pages/Saved"
import Settings from "@/pages/Settings"
import Sources from "@/pages/Sources"
import Today from "@/pages/Today"

const NAV: { page: string; label: string; icon: ReactNode }[] = [
  { page: "today", label: "Today", icon: <SunIcon /> },
  { page: "jobs", label: "Jobs", icon: <BriefcaseIcon /> },
  { page: "reading", label: "Reading", icon: <BookOpenIcon /> },
  { page: "cases", label: "Case studies", icon: <FlaskIcon /> },
  { page: "saved", label: "Saved", icon: <BookmarkSimpleIcon /> },
  { page: "runs", label: "Agent runs", icon: <RobotIcon /> },
  { page: "sources", label: "Sources", icon: <RssIcon /> },
  { page: "settings", label: "Profile and settings", icon: <GearIcon /> },
  { page: "how", label: "How this works", icon: <QuestionIcon /> },
]

const PAGES: Record<string, () => ReactNode> = {
  today: () => <Today />, jobs: () => <Jobs />, reading: () => <Reading />, cases: () => <Cases />, saved: () => <Saved />,
  runs: () => <Runs />, sources: () => <Sources />, settings: () => <Settings />, how: () => <How />,
}

interface StatusCtx { status: Status | null; error: string | null; reload: () => void }
const Ctx = createContext<StatusCtx>({ status: null, error: null, reload: () => {} })
export const useStatus = () => useContext(Ctx)

function useTheme() {
  const read = () => { try { return localStorage.getItem("theme") } catch { return null } }
  const [theme, setTheme] = useState<string | null>(() => read() ?? "light")
  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)")
    const apply = () => document.documentElement.classList.toggle("dark", theme ? theme === "dark" : media.matches)
    apply()
    media.addEventListener("change", apply)
    return () => media.removeEventListener("change", apply)
  }, [theme])
  return () => {
    const next = document.documentElement.classList.contains("dark") ? "light" : "dark"
    try { localStorage.setItem("theme", next) } catch { /* the choice just won't persist */ }
    setTheme(next)
  }
}

export default function App() {
  const route = useRoute()
  const [busy, setBusy] = useState(false)
  const { data: status, error, reload } = useApi<Status>("/api/status", busy ? 3000 : 15000)
  useEffect(() => setBusy(!!status && (status.runs.length > 0 || status.queue.queued + status.queue.running > 0)), [status])
  const toggleTheme = useTheme()
  const page = PAGES[route.page] ? route.page : "today"
  const label = NAV.find((n) => n.page === page)?.label ?? "Today"
  useEffect(() => { document.title = `${label} · SignalDesk` }, [label])

  const model = status?.model
  return (
    <Ctx.Provider value={{ status, error, reload }}>
      <div className="flex h-dvh min-h-0 flex-col lg:flex-row">
        <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-background focus:p-2">Skip to content</a>
        <Sidebar className="h-auto w-full shrink-0 border-e-0 border-b lg:h-dvh lg:w-56 lg:border-e lg:border-b-0">
          <SidebarHeader className="flex flex-row items-center justify-between gap-2 px-4 py-3">
            <span className="flex items-center gap-2 font-heading text-xl font-medium"><span aria-hidden="true" className="brand-mark">s</span>SignalDesk</span>
            <Button variant="ghost" size="icon-sm" onClick={toggleTheme} aria-label="Switch between light and dark theme">
              <MoonIcon className="size-4 dark:hidden" /><SunIcon className="hidden size-4 dark:block" />
            </Button>
          </SidebarHeader>
          <SidebarContent className="px-2 pb-2">
            <nav aria-label="Main">
              <SidebarGroup className="flex flex-row flex-wrap gap-0.5 lg:flex-col">
                {NAV.map((n) => (
                  <SidebarItem key={n.page} icon={n.icon} active={page === n.page} onClick={() => go(n.page)} className="w-auto lg:w-full">
                    {n.label}
                  </SidebarItem>
                ))}
              </SidebarGroup>
            </nav>
          </SidebarContent>
          <SidebarFooter className="mt-auto hidden flex-col items-start gap-1 px-4 py-4 text-xs lg:flex">
            {error ? (
              <StatusIndicator variant="destructive">SignalDesk server not answering</StatusIndicator>
            ) : model ? (
              <>
                <StatusIndicator variant={model.ready ? "success" : "warning"}>{model.ready ? "Model ready" : model.reachable ? "Different model running" : "Model offline"}</StatusIndicator>
                <span className="break-all text-muted-foreground">{model.ready ? model.configured : "Collection still works; analysis waits"}</span>
              </>
            ) : null}
          </SidebarFooter>
        </Sidebar>
        <main id="main" tabIndex={-1} className="flex min-h-0 min-w-0 flex-1 flex-col overflow-y-auto outline-none">
          {PAGES[page]()}
        </main>
      </div>
    </Ctx.Provider>
  )
}
