from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass

from psycopg_pool import ConnectionPool


@dataclass(frozen=True)
class Database:
    pool: ConnectionPool

    @contextmanager
    def connect(self):
        with self.pool.connection() as conn:
            yield conn


MIGRATION_SQL = """
create table if not exists leads (
  id text primary key,
  created_at timestamptz not null default now(),
  source text not null default 'meta',
  meta_lead_id text unique,
  name text,
  phone_e164 text,
  email text,
  consent_text text,
  consent_timestamp timestamptz,
  language text default 'en',
  status text not null default 'new',
  do_not_contact boolean not null default false,
  -- Brampton buyer profile fields (v2)
  tags jsonb not null default '[]'::jsonb,
  readiness_score integer,
  readiness_tier text,
  buyer_profile jsonb,
  scores jsonb
);

create table if not exists events (
  id bigserial primary key,
  lead_id text references leads(id) on delete cascade,
  type text not null,
  payload_json jsonb not null,
  created_at timestamptz not null default now()
);

create table if not exists calls (
  id bigserial primary key,
  lead_id text references leads(id) on delete cascade,
  retell_call_id text unique,
  twilio_call_sid text,
  started_at timestamptz,
  ended_at timestamptz,
  duration_sec integer,
  outcome text,
  disconnection_reason text,
  transcript_text text,
  extracted_json jsonb,
  created_at timestamptz not null default now()
);

create table if not exists messages (
  id bigserial primary key,
  lead_id text references leads(id) on delete cascade,
  direction text not null,
  channel text not null,
  twilio_message_sid text,
  body text not null,
  status text,
  created_at timestamptz not null default now()
);

create table if not exists jobs (
  id bigserial primary key,
  type text not null,
  dedupe_key text,
  payload jsonb not null default '{}'::jsonb,
  run_at timestamptz not null default now(),
  status text not null default 'queued',
  attempts integer not null default 0,
  max_attempts integer not null default 3,
  locked_at timestamptz,
  locked_by text,
  last_error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists jobs_type_dedupe_key_uidx on jobs(type, dedupe_key)
where dedupe_key is not null;

-- v2: buyer profile columns (safe to run on existing DB — add if not exists)
alter table leads add column if not exists tags jsonb not null default '[]'::jsonb;
alter table leads add column if not exists readiness_score integer;
alter table leads add column if not exists readiness_tier text;
alter table leads add column if not exists buyer_profile jsonb;
alter table leads add column if not exists scores jsonb;

-- v2: knowledge copilot
create table if not exists knowledge_chunks (
  id bigserial primary key,
  doc_id text not null,
  source_path text not null,
  chunk_index integer not null,
  heading text,
  body text not null,
  topic text,
  jurisdiction text default 'ontario',
  audience text default 'agent',
  risk_level text default 'low',
  requires_professional_review boolean default false,
  embedding jsonb,   -- float array stored as JSON; cosine similarity computed in Python
  created_at timestamptz not null default now(),
  unique (doc_id, chunk_index)
);

create index if not exists knowledge_chunks_doc_id_idx on knowledge_chunks(doc_id);
"""


def create_database(database_url: str) -> Database:
    pool = ConnectionPool(conninfo=database_url, min_size=1, max_size=10, open=True)
    return Database(pool=pool)


def migrate(db: Database) -> None:
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(MIGRATION_SQL)
        conn.commit()

