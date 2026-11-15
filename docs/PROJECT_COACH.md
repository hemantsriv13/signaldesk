# Project Coach

## Scope and checkpoint

Step 1 implements laptop collection, deterministic task selection, local human
responses, exports to the data folder, and a desktop Projects page. Stop for
owner review before cloud sync. Steps 2–4 are not implemented. Verification and
any remaining access limitations are recorded in HANDOFF_PROJECTS.md.

The coach is bounded ordinary code, like the four existing agents. It does not
write code, run models in sibling projects, execute repository instructions, or
change those clones. A model is unnecessary for the first version. If optional
polish is added later, templates remain authoritative and validation failure or
an unavailable model must return the template without blocking selection.

## Local contract

Configuration uses repeated `[[project]]` entries with `name`, `path`, and `kind`.
Kinds identify the pushback, nextword and signaldesk adapters. Resolve configured
paths explicitly; report missing clones as unavailable without failing the run.
Read Git branch, last commit time, and dirty state without changing the index,
checking out branches, running hooks, or printing repository content to logs.

Each source adapter yields stable item identities, source age, result-blocking
priority, review text, pass criteria, evidence facts, and export provenance.
Store task snapshots and responses in SignalDesk SQLite. Responses record UTC
time and `human` provenance. Enforce allowed verdicts per task type and reject
answers to read-only reminders. Use a unique response identity for later sync.

Blind pushback cards use an allowlist of source fields. Grader labels, scores,
reasons and verdicts must never enter the task payload, including nested metadata
and explanatory text. Test both stored snapshots and serialized API output.

Select a persisted daily batch of at most three answerable tasks. Prefer one
per available project, then fill unused slots from remaining candidates; within
each project put result-blocking work first, then oldest, then stable identity.
Answered source identities never return, even after a restart. Refresh must not
create a second daily allowance. Keep up to three read-only laptop reminders
separate from that allowance; a missing pushback sheet becomes a reminder, never
a model run. Skip defers an item without fabricating a human verdict.

Every task has two plain sentences under “What this is”, a concrete sourced fact
under “Why it matters”, and an explicit next result it unlocks. Never invent role
counts or README claims. Counts may come from the copied database; project-result
facts must come from verified project documentation. Keep learning relevance
separate from unsupported claims that a task will secure employment.

Export commands write one project file below the selected data home's
`project-exports/<timestamp>-<id>` directory. Completed exports are published by
renaming a `.pending` directory; a failed export leaves its incomplete directory
for inspection. Export never invokes a consumer or writes back into a clone.

- Pushback: CSV with the existing label-sheet columns, plus `human_at` and
  `input_origin`. Only allowlisted columns are exported; grader fields are absent.
- NextWord: one ZIP per project, containing the existing Markdown sheet names,
  key.json, and a human-input audit JSON with timestamps and original notes.
  The ZIP retains multiple set filenames because `compare_review.py --sheets`
  expects them. Extract into a separate data-folder directory for that reader;
  do not extract into the clone. Multiline notes become one line in Markdown;
  the audit JSON retains the original. Changed sources, mappings or conflicting
  external human notes/verdicts block export. Existing verdicts are never silently
  overwritten. `compare_review.py` also needs its existing ai_review.json for
  AI comparison; that file is not generated or altered by SignalDesk.
- SignalDesk: versioned JSON (`signaldesk-project-responses-v1`) containing
  analysis IDs, verdicts, notes, UTC response times and human provenance.

NextWord's existing blank `Verdict:` markers and key.json map the human-review
backlog to saved results. The adapter reads bigram `cases`, tutor `runs`, and MLP
`results`, including recorded engine facts or calculation lines. A result without
a mapped sheet becomes a laptop setup reminder, not an invented review item.

Daily batches use the laptop's local calendar date. Collection is explicit from
Projects, Agent runs, or `python -m signaldesk.projects collect --home <copy>`.
The normal sweep has not been changed. Once prepared, the day's batch is frozen,
including skipped cards; answered source IDs never return on later days. No
projects configured does not freeze an empty batch. After changing a prepared
configuration, the next daily batch reads it. Project Git metadata is a snapshot
at collection time, not a live status claim.

Responses are immutable in this version. A repeated identical save is harmless;
a different second verdict is rejected. Skip means “skip today”, with no human
verdict or export row. Weekly counts start on Monday in the laptop's timezone.
The SQLite migration is additive and leaves prior jobs and briefings intact.

## Running Step 1

Add the three entries shown in config.example.toml to a copied home's config.toml.
Keep delivery credentials out of the copy. Then, with a functional Python env:

```powershell
.venv\Scripts\python -m pytest -q
.venv\Scripts\python -m signaldesk.projects collect --home <copied-data-home>
.venv\Scripts\python -m signaldesk.projects export --home <copied-data-home>
.venv\Scripts\python -m signaldesk --home <copied-data-home> --no-start-model
```

Open Projects in the desktop shell, prepare the batch, read the evidence, and
save a verdict or skip today. Collection and export contain no network calls.
The desktop page uses the existing origin, login and CSRF protections. No
new hosting, service, queue worker, model request, or phone dependency was added.

## Deferred designs

### Tailscale tunnel

Keep the current loopback laptop API and Supabase reader. A future tunnel needs
an explicit owner decision, authenticated HTTPS, restricted devices and origins,
and tests that unauthenticated users cannot read private data. Do not configure
Tailscale, firewall rules or network listeners as part of Project Coach.

### Live model questions from the phone

A future request would enter the existing persistent queue with bounded input,
an explicit user action, cancellation and a visible laptop-offline state. It
must not expose the Colibri port or let text execute commands. Evaluate reliable
answer validation before offering it; neither local model is currently trusted
for free text. Today's cards always remain usable with templates alone.

### Writing responses into sibling clones

Keep exports as reviewable files in SignalDesk's data folder. A future explicit
import action should show destination paths, source IDs and changed fields,
validate the consumer schema, detect conflicting human answers, and make a
recoverable backup. Ask before touching pushback or nextword. Never overwrite
an existing human verdict silently or run model evaluation during import.

### Commits and pushes in sibling repositories

No automatic Git mutation. After a separately authorized import, show the owner
the diff and exact proposed commit message. Obtain authorization before commits
or pushes there, and again before any GitHub push unless already authorized for
that concrete operation. Never include SignalDesk's private data in a commit.
