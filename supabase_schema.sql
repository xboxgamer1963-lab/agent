-- Account Enrichment Pipeline — Supabase schema
-- Run this once in the Supabase SQL Editor (Project → SQL Editor → New query),
-- then restart the backend. Mirrors the previous SQLite schema, with JSON
-- fields stored as native JSONB instead of serialized text.

create table if not exists runs (
    id          bigint generated always as identity primary key,
    created_at  timestamptz not null,
    value_prop  text not null,
    sheet_id    text not null,
    status      text not null default 'pending',
    total       integer default 0,
    done        integer default 0,
    enriched    integer default 0,
    dropped     integer default 0,
    errors      integer default 0
);

create table if not exists accounts (
    id                bigint generated always as identity primary key,
    run_id            bigint not null references runs(id),
    name              text not null,
    domain            text,
    row_index         integer,
    status            text not null default 'pending',
    batch_number      integer,
    hypothesis_1      jsonb,
    hypothesis_2      jsonb,
    news              jsonb,
    linkedin          jsonb,
    eval_1            jsonb,
    eval_2            jsonb,
    search_commands   jsonb,
    dossier           jsonb,
    homepage          text,
    outreach_angles   jsonb,
    pipedrive_org_id  text,
    pipedrive_note_id text,
    error_message     text,
    retry_count       integer default 0,
    updated_at        timestamptz
);

create table if not exists logs (
    id          bigint generated always as identity primary key,
    account_id  bigint not null references accounts(id),
    step        text not null,
    message     text not null,
    created_at  timestamptz not null
);

create index if not exists idx_accounts_run_id on accounts(run_id);
create index if not exists idx_logs_account_id on logs(account_id, created_at);

-- The backend authenticates with the service_role key, which bypasses RLS
-- entirely. Enabling RLS with no policies just means the anon/public key
-- (if it were ever used) gets zero access by default — a safe posture.
alter table runs enable row level security;
alter table accounts enable row level security;
alter table logs enable row level security;
