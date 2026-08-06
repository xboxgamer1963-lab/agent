-- Onboarding + multi-tenancy migration — run once in the Supabase SQL Editor,
-- after supabase_schema.sql. Adds a per-user profile (captured during
-- onboarding) and ties runs to the user that started them.

create table if not exists profiles (
    user_id              uuid primary key references auth.users(id) on delete cascade,
    email                text,
    role                 text,
    company              text,
    referral_source      text,
    icp                  text,
    target_market        text,
    audience             text,
    industry             text,
    target_roles         text,
    good_score           integer not null default 7,
    tone                 text not null default 'professional',
    onboarding_completed boolean not null default false,
    created_at           timestamptz not null default now(),
    updated_at           timestamptz not null default now()
);

-- Same posture as the base schema: the backend talks to Supabase with the
-- service_role key, which bypasses RLS entirely. Enabling RLS with no
-- policies just means the anon/public key gets zero direct access.
alter table profiles enable row level security;

alter table runs add column if not exists user_id uuid references auth.users(id);
create index if not exists idx_runs_user_id on runs(user_id);

-- Denormalized onto accounts too, so account/analytics queries can filter
-- directly without joining through runs.
alter table accounts add column if not exists user_id uuid references auth.users(id);
create index if not exists idx_accounts_user_id on accounts(user_id);
