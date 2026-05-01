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
  do_not_contact boolean not null default false
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
"""


def create_database(database_url: str) -> Database:
    pool = ConnectionPool(conninfo=database_url, min_size=1, max_size=10, open=True)
    return Database(pool=pool)


def migrate(db: Database) -> None:
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(MIGRATION_SQL)
        conn.commit()

