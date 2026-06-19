-- FreightVoice fake-TMS tables, mirroring faketms/db.py (SQLite) so the
-- InsForgeStore backend is a drop-in. Timestamps are stored as ISO text to
-- match what the Python service writes. No RLS: this is a trusted server-side
-- TMS accessed with the project (admin) API key; production would add policies.

create table if not exists public.loads (
  load_id             text primary key,
  shipper             text,
  consignee           text,
  commodity           text,
  expected_pieces     integer,
  expected_weight_lbs double precision,
  scheduled_delivery  text,
  equipment_type      text,
  status              text default 'pending',
  invoice_number      text,
  delivered_at        text
);

create table if not exists public.pods (
  id          bigserial primary key,
  load_id     text references public.loads(load_id),
  record_json text,
  readback    text,
  clean       boolean,
  created_at  text
);

create table if not exists public.discrepancies (
  id                 bigserial primary key,
  load_id            text references public.loads(load_id),
  code               text,
  severity           text,
  message            text,
  transcript_excerpt text,
  created_at         text
);
