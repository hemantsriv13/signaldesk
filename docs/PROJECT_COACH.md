# Project Coach

Bounded ordinary code, like the other agents: no model, no free text from a model, no repository
code run except each repo's own tests. Rules choose up to three reviews a day; templates explain them.

## 1. Daily batch (laptop)

- `[[project]]` entries (`name`, `path`, `kind` = pushback | nextword | signaldesk, optional
  `check_python`). Missing or unreadable clones become laptop reminders; nothing fails.
- Adapters read: pushback `labels/*.csv` rows with an empty `human_label` (allow-listed columns
  only; evidence is the row's own `## <probe>` section of the data sheet); NextWord human-review
  sheets with a blank `Verdict:` mapped by `key.json` (turns and engine facts only; never automatic
  checks, `ai_review.json` or model names); SignalDesk job-fit and case-study analyses.
- Selection: one task per project first, then fill to three; result-blocking first, then oldest
  (timestamps compared as UTC instants). Frozen per laptop day; answered items never return.
- **Why it matters** cites facts read at collection time: a README line that must still say the quoted
  text (re-checked by `check_why`), and counts from your data (open reviews, shortlisted roles and
  how many mention the project's skill). Text without a verifiable fact is rejected and the item
  becomes a laptop reminder. Pushback with no open rows gives a counted reminder; no model is run.
- Answers are immutable human input (`via` desktop or phone); a different second answer is refused.

## 2. Exports (laptop)

`python -m signaldesk.projects export --home <home>` or *Export saved answers*: pushback CSV
(sheet columns + `human_at`, `input_origin`), NextWord ZIP (sheets, `key.json`, audit JSON),
SignalDesk JSON v1, under `<home>\project-exports\<time>-<id>`. A failed check names itself.

## 3. Phone (cloud copy)

`cloud/project_coach.sql` adds `signaldesk_project_tasks` (laptop writes, owner reads) and
`signaldesk_project_responses` (owner inserts only; verdict must be allowed by the task; no update,
delete or import columns). The laptop pushes phone-safe cards: SignalDesk cards never carry
profile-fact notes, recorded inputs or full articles (postings capped at 4,000 characters). Phone
answers are imported through the same rules; conflicts keep the earlier answer and are shown.
`[coach] auto_prepare = true` prepares each day's batch while SignalDesk runs (off by default).

The Android app's Projects tab queues answers on the phone with a phone-made id, sends them when
online, recognises a lost reply instead of duplicating, and clears cards, queue, skips, live pairing
and reminders on sign-out (warning first if answers are unsent). Reminders are Android local
notifications at times you set, off by default, generic text, no push server.

## 4. Live phone access (Tailscale)

See [LAN_AND_PANEL.md §8](LAN_AND_PANEL.md). The signed-in HTTPS listener bound to the tailnet
address; phone codes reach only `/api/phone/*`. The app uses the laptop when it answers within four
seconds and the cloud copy otherwise. No phone route uses the model queue, so phone requests never
wait behind batch analysis; any future phone model request must be queued with a lower priority
number than batch work (the queue already takes the lowest number first).

## 5. Writing answers into the clones

`python -m signaldesk.projects writeback --home <home>`, *Write answers to projects*, or
`[writeback] auto = true` (every 30 minutes). Per repo, only when listed in `[writeback] write`;
pushed only when also in `[writeback] push`. Work happens in a git worktree under
`<home>\project-worktrees\<repo>` on branch `phone-review` (your open clone is not switched or
edited). Allow-list: pushback `labels/*.csv` (human_label, human_note); NextWord
`evals/local_ai/human_review/*.md` (Verdict, Note). SignalDesk answers are never committed.
It stops on uncommitted work in the clone, a non-fast-forward `phone-review`, format drift, any
change outside the allow-list, or a failing repo check (pushback: tests and `labels score`;
NextWord: unittest and `compare_review.py`). Commits use your git identity and say they came from
SignalDesk review. Main is never committed or pushed.

**Found in the dry run on scratch copies (2026-11-16):** both repos' own tests reject filled answers
in their current committed sheets. Pushback pins the label CSV hashes in
`reports/run-provenance.json`; NextWord requires the committed sheets to stay blank. So with the
repos as they are, write-back always stops before committing. This needs your decision (see HANDOFF_PROJECTS.md).
