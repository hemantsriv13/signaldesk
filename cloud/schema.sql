-- Run in your own Supabase project's SQL editor. No public reads or client writes.
create table if not exists public.signaldesk_digests (
  id uuid not null,
  owner_id uuid not null references auth.users(id) on delete cascade,
  created_at timestamptz not null,
  synced_at timestamptz not null default now(),
  payload jsonb not null,
  primary key (owner_id, id)
);
alter table public.signaldesk_digests enable row level security;
drop policy if exists "Read own digests" on public.signaldesk_digests;
create policy "Read own digests" on public.signaldesk_digests for select
  to authenticated using ((select auth.uid()) = owner_id);
revoke all on public.signaldesk_digests from anon, authenticated;
grant select on public.signaldesk_digests to authenticated;
grant all on public.signaldesk_digests to service_role;
-- Uploads use the service-role key only on the laptop. Never put that key in web/mobile builds.
