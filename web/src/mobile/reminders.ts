// Daily local reminders on the phone. Off until you turn them on; scheduled by Android itself,
// so no push server, account or network is involved. The text is generic on purpose: nothing
// about your projects or job search appears on the lock screen.
import { Capacitor } from "@capacitor/core"
import { LocalNotifications } from "@capacitor/local-notifications"

export interface ReminderSettings { on: boolean; times: string[] }      // "HH:MM", local time
const KEY = "signaldesk-reminders"
const IDS = [7101, 7102, 7103]
export const MAX_TIMES = IDS.length
export const DEFAULT: ReminderSettings = { on: false, times: ["09:00"] }

export const available = () => Capacitor.isNativePlatform()

export function load(read: (k: string) => string | null): ReminderSettings {
  try {
    const s = JSON.parse(read(KEY) ?? "null") as ReminderSettings | null
    return s && typeof s.on === "boolean" && Array.isArray(s.times) ? { on: s.on, times: s.times.filter(valid).slice(0, MAX_TIMES) } : DEFAULT
  } catch { return DEFAULT }
}

export const valid = (t: string) => /^([01]\d|2[0-3]):[0-5]\d$/.test(t)

/** Cancel ours, then schedule one repeating reminder per time. Returns a message for the screen. */
export async function apply(s: ReminderSettings, write: (k: string, v: string | null) => void): Promise<string> {
  const times = [...new Set(s.times.filter(valid))].slice(0, MAX_TIMES)
  if (!available()) return "Reminders work in the Android app only."
  await LocalNotifications.cancel({ notifications: IDS.map((id) => ({ id })) })
  if (!s.on || !times.length) { write(KEY, JSON.stringify({ on: false, times: times.length ? times : DEFAULT.times })); return "Reminders are off." }
  let perm = await LocalNotifications.checkPermissions()
  if (perm.display !== "granted") perm = await LocalNotifications.requestPermissions()
  if (perm.display !== "granted") {
    write(KEY, JSON.stringify({ on: false, times }))
    return "Android did not allow notifications. Turn them on for SignalDesk in Android settings."
  }
  await LocalNotifications.schedule({ notifications: times.map((t, i) => {
    const [hour, minute] = t.split(":").map(Number)
    return { id: IDS[i], title: "SignalDesk", body: "Your project reviews are waiting.", schedule: { on: { hour, minute }, allowWhileIdle: true } }
  }) })
  write(KEY, JSON.stringify({ on: true, times }))
  return `Reminders set for ${times.join(" and ")} each day.`
}

/** Sign-out: stop reminders for this phone. The chosen times are kept for next time, switched off. */
export async function stop(read: (k: string) => string | null, write: (k: string, v: string | null) => void) {
  const s = load(read)
  write(KEY, JSON.stringify({ ...s, on: false }))
  if (available()) await LocalNotifications.cancel({ notifications: IDS.map((id) => ({ id })) })
}
