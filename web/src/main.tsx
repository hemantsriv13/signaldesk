import { StrictMode, lazy, Suspense } from "react"
import { createRoot } from "react-dom/client"
import "./index.css"
import "./lib/offline-icons"
import App from "./App.tsx"

const Mobile = lazy(() => import("./Mobile"))
const mobile = import.meta.env.VITE_SIGNALDESK_MOBILE === "true"

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {mobile ? <Suspense fallback={<p>Opening SignalDesk…</p>}><Mobile /></Suspense> : <App />}
  </StrictMode>,
)
