import { test } from "node:test"
import assert from "node:assert/strict"
import { liveAnswer, liveToday, validLive } from "../src/mobile/live.ts"

const L = { url: "https://laptop.tail1234.ts.net:8443/", token: "sdm_abc" }
const answer = { id: "id-1", task_id: "t/1", verdict: "pass", note: "", answered_at: "2026-11-16T06:00:00Z", project: "p", title: "t", state: "waiting" as const }
const reply = (status: number, body: unknown = {}) => (async () => new Response(JSON.stringify(body), { status })) as unknown as typeof fetch

test("only https addresses with a phone code are accepted", () => {
  assert.equal(validLive(L), true)
  assert.equal(validLive({ ...L, url: "http://laptop.tail1234.ts.net:8443/" }), false)
  assert.equal(validLive({ ...L, token: "sdp_panel" }), false)
  assert.equal(validLive({ ...L, url: "https://user:pw@laptop.ts.net/" }), false)
  assert.equal(validLive(null), false)
})

test("an unreachable laptop means fall back, not fail", async () => {
  const down = (async () => { throw new TypeError("Failed to fetch") }) as unknown as typeof fetch
  assert.equal(await liveToday(L, 100, down), null)
  assert.deepEqual(await liveAnswer(L, answer, 100, down), { ok: false, offline: true })
  assert.equal(await liveToday(L, 100, reply(503)), null)
})

test("an unpaired phone is told so, and its answer goes to the cloud instead", async () => {
  assert.equal(await liveToday(L, 100, reply(401)), "unpaired")
  assert.deepEqual(await liveAnswer(L, answer, 100, reply(401)), { ok: false, offline: true })
})

test("answers map onto the queue's rules", async () => {
  assert.deepEqual(await liveAnswer(L, answer, 100, reply(200, { saved: true })), { ok: true })
  assert.equal((await liveAnswer(L, answer, 100, reply(409))).ok === false && (await liveAnswer(L, answer, 100, reply(409)) as { code?: string }).code, "23505")
  const refused = await liveAnswer(L, answer, 100, reply(400))
  assert.equal(refused.ok, false); assert.equal((refused as { offline: boolean }).offline, false)
})

test("the token goes in the Authorization header and the task id is encoded", async () => {
  let seen: { url: string; auth: string | null } | null = null
  const spy = (async (url: string, init: RequestInit) => { seen = { url, auth: new Headers(init.headers).get("authorization") }; return new Response("{}", { status: 200 }) }) as unknown as typeof fetch
  await liveAnswer(L, answer, 100, spy)
  assert.deepEqual(seen, { url: "https://laptop.tail1234.ts.net:8443/api/phone/projects/t%2F1/answer", auth: "Bearer sdm_abc" })
})
