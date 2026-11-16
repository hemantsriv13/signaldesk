-- Project Coach on the phone. Run once in your own Supabase project's SQL editor, after schema.sql.
-- Additive: it does not touch signaldesk_digests. Safe to run again.
--
-- Tasks:     the laptop (service-role key) writes today's batch; you can only read your own rows.
-- Responses: the phone inserts your answers; it can never change or delete one. The laptop reads them,
--            imports them into its own database and marks them imported (service role only).

create table if not exists public.signaldesk_project_tasks (
  id uuid not null,
  owner_id uuid not null references auth.users(id) on delete cascade,
  day date not null,                         -- the laptop's local calendar day
  project text not null check (char_length(project) <= 80),
  kind text not null check (kind in ('label_reply', 'review_answer', 'judge_analysis', 'laptop_reminder')),
  status text not null default 'open' check (status in ('open', 'answered', 'skipped')),
  payload jsonb not null,                    -- phone-safe card: no grader output, profile facts or full articles
  created_at timestamptz not null,
  synced_at timestamptz not null default now(),
  primary key (id)
);
create index if not exists signaldesk_project_tasks_owner_day on public.signaldesk_project_tasks (owner_id, day);

create table if not exists public.signaldesk_project_responses (
  id uuid not null primary key,              -- made on the phone, so a retried send cannot duplicate
  owner_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
  task_id uuid not null references public.signaldesk_project_tasks(id) on delete cascade,
  verdict text not null check (verdict in ('pass', 'fail', 'unclear', 'correct', 'minor', 'wrong', 'agree', 'disagree', 'unsure')),
  note text not null default '' check (char_length(note) <= 4000),
  answered_at timestamptz not null,          -- phone clock when you saved it (may be offline)
  received_at timestamptz not null default now(),
  imported_at timestamptz,                   -- set by the laptop
  import_result text check (import_result in ('saved', 'duplicate', 'conflict', 'rejected')),
  unique (owner_id, task_id)                 -- one answer per task, as on the laptop
);

alter table public.signaldesk_project_tasks enable row level security;
alter table public.signaldesk_project_responses enable row level security;

drop policy if exists "Read own project tasks" on public.signaldesk_project_tasks;
create policy "Read own project tasks" on public.signaldesk_project_tasks for select
  to authenticated using ((select auth.uid()) = owner_id);

drop policy if exists "Read own project responses" on public.signaldesk_project_responses;
create policy "Read own project responses" on public.signaldesk_project_responses for select
  to authenticated using ((select auth.uid()) = owner_id);

-- Insert only: your own row, for your own answerable task, with a verdict that task allows,
-- and without pre-filling the laptop's import columns.
drop policy if exists "Answer own project task" on public.signaldesk_project_responses;
create policy "Answer own project task" on public.signaldesk_project_responses for insert
  to authenticated with check (
    (select auth.uid()) = owner_id
    and imported_at is null and import_result is null
    and exists (
      select 1 from public.signaldesk_project_tasks t
      where t.id = task_id and t.owner_id = (select auth.uid())
        and t.kind <> 'laptop_reminder'
        and (t.payload -> 'verdicts') ? verdict
    )
  );

revoke all on public.signaldesk_project_tasks from anon, authenticated;
revoke all on public.signaldesk_project_responses from anon, authenticated;
grant select on public.signaldesk_project_tasks to authenticated;
grant select on public.signaldesk_project_responses to authenticated;
grant insert (id, task_id, verdict, note, answered_at) on public.signaldesk_project_responses to authenticated;
grant all on public.signaldesk_project_tasks to service_role;
grant all on public.signaldesk_project_responses to service_role;
-- No update or delete grant for authenticated users: answers are immutable from the phone.
