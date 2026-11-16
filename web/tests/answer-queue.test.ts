// node --test web/tests/answer-queue.test.ts   (Node 22.6+ strips the types)
import { test } from "node:test"
import assert from "node:assert/strict"
import { clearAccount, discard, enqueue, flush, keys, readNotices, readQueue, skip, skippedToday, type KeyValue, type QueuedAnswer, type SendResult } from "../src/mobile/answer-queue.ts"

function memory(): KeyValue & { data: Map<string, string> } {
  const data = new Map<string, string>()
  return { data, get: (k) => data.get(k) ?? null, set: (k, v) => { if (v === null) data.delete(k); else data.set(k, v) } }
}
const answer = (n: number) => ({ id: `id-${n}`, task_id: `task-${n}`, verdict: "pass", note: "", answered_at: "2026-11-16T06:00:00Z", project: "pushback", title: "Judge" })

test("answers wait offline and are sent in order when back online", async () => {
  const s = memory()
  enqueue(s, "u1", answer(1)); enqueue(s, "u1", answer(2))
  const offline = await flush(s, "u1", async () => ({ ok: false, offline: true }), async () => null)
  assert.equal(offline.sent, 0); assert.equal(readQueue(s, "u1").length, 2)
  const order: string[] = []
  const online = await flush(s, "u1", async (a) => { order.push(a.id); return { ok: true } }, async () => null)
  assert.deepEqual(order, ["id-1", "id-2"]); assert.equal(online.sent, 2); assert.equal(readQueue(s, "u1").length, 0)
  assert.equal(s.get(keys("u1").queue), null)
})

test("a lost reply is recognised on retry instead of duplicating", async () => {
  const s = memory()
  enqueue(s, "u1", answer(1))
  const r = await flush(s, "u1", async () => ({ ok: false, offline: false, code: "23505" }), async () => "id-1")
  assert.equal(r.sent, 1); assert.deepEqual(r.notices, []); assert.equal(readQueue(s, "u1").length, 0)
})

test("an item answered elsewhere is dropped with a notice, never overwritten", async () => {
  const s = memory()
  enqueue(s, "u1", answer(1))
  const r = await flush(s, "u1", async () => ({ ok: false, offline: false, code: "23505" }), async () => "someone-else")
  assert.equal(r.sent, 0); assert.equal(r.notices.length, 1); assert.equal(readNotices(s, "u1").length, 1)
  assert.equal(readQueue(s, "u1").length, 0)
})

test("a refused answer stays visible as failed and is not retried automatically", async () => {
  const s = memory()
  enqueue(s, "u1", answer(1)); enqueue(s, "u1", answer(2))
  let calls = 0
  const send = async (a: QueuedAnswer): Promise<SendResult> => { calls++; return a.id === "id-1" ? { ok: false, offline: false, code: "42501", message: "refused" } : { ok: true } }
  await flush(s, "u1", send, async () => null)
  const q = readQueue(s, "u1")
  assert.equal(q.length, 1); assert.equal(q[0].state, "failed"); assert.equal(q[0].error, "refused")
  await flush(s, "u1", send, async () => null)
  assert.equal(calls, 2, "failed item not resent")
  assert.equal(discard(s, "u1", "id-1").length, 0)
})

test("one queued answer per task", () => {
  const s = memory()
  enqueue(s, "u1", answer(1))
  assert.equal(enqueue(s, "u1", { ...answer(1), id: "other", verdict: "fail" }).length, 1)
})

test("accounts are separate and sign-out clears only that account", () => {
  const s = memory()
  enqueue(s, "u1", answer(1)); enqueue(s, "u2", answer(2))
  s.set(keys("u1").tasks, "[]"); skip(s, "u1", "2026-11-16", "task-9")
  clearAccount(s, "u1")
  assert.equal(readQueue(s, "u1").length, 0); assert.equal(s.get(keys("u1").tasks), null)
  assert.deepEqual(skippedToday(s, "u1", "2026-11-16"), [])
  assert.equal(readQueue(s, "u2").length, 1)
})

test("skips last for one batch day only", () => {
  const s = memory()
  skip(s, "u1", "2026-11-16", "a"); skip(s, "u1", "2026-11-16", "b")
  assert.deepEqual(skippedToday(s, "u1", "2026-11-16"), ["a", "b"])
  skip(s, "u1", "2026-11-17", "c")
  assert.deepEqual(skippedToday(s, "u1", "2026-11-16"), [])
})

test("flush reports which tasks were sent so the screen can mark them answered", async () => {
  const s = memory()
  enqueue(s, "u1", answer(1)); enqueue(s, "u1", answer(2))
  const r = await flush(s, "u1", async (a) => a.id === "id-1" ? { ok: true } : { ok: false, offline: false, code: "23505" }, async () => "id-2")
  assert.deepEqual(r.sentTasks, ["task-1", "task-2"])
})
