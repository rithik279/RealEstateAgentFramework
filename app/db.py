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

-- v4: area label (deterministic from area code, never AI-inferred)
alter table leads add column if not exists area text;
create index if not exists leads_area_idx on leads(area);

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

-- v3: MLS listings cache (populated by RESO sync pipeline)
create table if not exists listings (
  id bigserial primary key,
  mls_number text unique not null,
  status text not null default 'Active',   -- Active | Sold | Expired | Terminated
  list_price integer,
  sold_price integer,
  address text,
  city text default 'Brampton',
  province text default 'ON',
  postal_code text,
  neighbourhood text,
  property_type text,
  property_subtype text,
  bedrooms integer,
  bathrooms integer,
  parking_spaces integer,
  garage_spaces integer,
  has_garage boolean default false,
  square_feet integer,
  lot_size_sqft numeric,
  year_built integer,
  stories integer,
  -- Basement (critical for Brampton buyers)
  basement_separate_entrance boolean default false,
  basement_suite boolean default false,
  basement_legal boolean default false,
  basement_finished boolean default false,
  basement_type text,
  -- Kitchen
  kitchen_condition text,   -- renovated | dated | unknown
  open_concept boolean default false,
  kitchen_features text,
  -- Financials
  property_tax_annual numeric,
  condo_fee_monthly numeric,
  -- Dates
  listed_date date,
  sold_date date,
  expiry_date date,
  days_on_market integer,
  -- Media
  photos jsonb default '[]'::jsonb,
  -- Full normalized payload
  normalized_data jsonb,
  -- Raw RESO payload (compliance audit)
  raw_reso jsonb,
  -- Sync metadata
  last_synced_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists listings_city_status_idx on listings(city, status);
create index if not exists listings_price_idx on listings(list_price) where status = 'Active';
create index if not exists listings_beds_idx on listings(bedrooms) where status = 'Active';

-- v3: compliance audit log
create table if not exists audit_log (
  id bigserial primary key,
  entity_type text not null,  -- 'lead' | 'listing' | 'copilot_query'
  entity_id text,
  action text not null,       -- 'viewed' | 'exported' | 'ai_queried' | 'shared'
  user_id text,
  details jsonb,
  created_at timestamptz not null default now()
);

create index if not exists audit_log_entity_idx on audit_log(entity_type, entity_id);
"""


def create_database(database_url: str) -> Database:
    pool = ConnectionPool(conninfo=database_url, min_size=1, max_size=10, open=True)
    return Database(pool=pool)


def migrate(db: Database) -> None:
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(MIGRATION_SQL)
        conn.commit()

