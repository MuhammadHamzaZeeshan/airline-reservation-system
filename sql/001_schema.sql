-- 001_schema.sql : logical schema (runs on any PostgreSQL 16; 002 distributes it on Citus).
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS vector;

-- ---------- reference data (replicated to every node by 002) ----------
CREATE TABLE IF NOT EXISTS airports (
  airport_id  integer PRIMARY KEY,
  code        text NOT NULL UNIQUE,
  name        text NOT NULL,
  city        text NOT NULL,
  country     text NOT NULL
);
CREATE TABLE IF NOT EXISTS airlines (
  airline_id  integer PRIMARY KEY,
  code        text NOT NULL UNIQUE,
  name        text NOT NULL
);
-- Seat layout per aircraft: rows are 3-3 (A-F). Business rows first, then premium, then economy.
CREATE TABLE IF NOT EXISTS aircraft_types (
  aircraft_id    integer PRIMARY KEY,
  name           text NOT NULL,
  business_rows  integer NOT NULL CHECK (business_rows >= 0),
  premium_rows   integer NOT NULL CHECK (premium_rows >= 0),
  economy_rows   integer NOT NULL CHECK (economy_rows > 0)
);
CREATE TABLE IF NOT EXISTS routes (
  route_id   integer PRIMARY KEY,
  origin_id  integer NOT NULL REFERENCES airports(airport_id),
  dest_id    integer NOT NULL REFERENCES airports(airport_id),
  CHECK (origin_id <> dest_id)
);

-- ---------- users + O(1) uniqueness registries ----------
CREATE SEQUENCE IF NOT EXISTS user_id_seq START 1;
CREATE TABLE IF NOT EXISTS users (
  user_id        bigint PRIMARY KEY DEFAULT nextval('user_id_seq'),
  username       text NOT NULL,
  email          text NOT NULL,
  password_hash  text NOT NULL,
  full_name      text NOT NULL DEFAULT '',
  is_admin       boolean NOT NULL DEFAULT false,
  created_at     timestamptz NOT NULL DEFAULT now()
);
-- Distributed by the unique value itself: the PRIMARY KEY on the owning shard IS the uniqueness guarantee.
CREATE TABLE IF NOT EXISTS username_registry (
  username  text PRIMARY KEY,
  user_id   bigint NOT NULL
);
CREATE TABLE IF NOT EXISTS email_registry (
  email    text PRIMARY KEY,
  user_id  bigint NOT NULL
);

-- ---------- flight-keyed tables (all hash-distributed on flight_id and co-located) ----------
CREATE TABLE IF NOT EXISTS flights (
  flight_id    bigint PRIMARY KEY,
  flight_no    text NOT NULL,
  airline_id   integer NOT NULL REFERENCES airlines(airline_id),
  origin_id    integer NOT NULL REFERENCES airports(airport_id),
  dest_id      integer NOT NULL REFERENCES airports(airport_id),
  aircraft_id  integer NOT NULL REFERENCES aircraft_types(aircraft_id),
  departure_ts timestamptz NOT NULL,
  arrival_ts   timestamptz NOT NULL,
  duration_min integer NOT NULL CHECK (duration_min > 0),
  stops        smallint NOT NULL DEFAULT 0 CHECK (stops BETWEEN 0 AND 3),
  price        numeric(10,2) NOT NULL CHECK (price >= 0),     -- cheapest (economy) fare, denormalised for sort/filter
  seats_left   integer NOT NULL CHECK (seats_left >= 0),      -- total across classes, maintained in the booking txn
  embedding    vector(8)
);

-- One row per class per flight. CHECK (available >= 0) is the last line of defence against overselling.
CREATE TABLE IF NOT EXISTS seat_inventory (
  flight_id  bigint NOT NULL,
  fare_class text   NOT NULL CHECK (fare_class IN ('ECONOMY','PREMIUM','BUSINESS')),
  total      integer NOT NULL CHECK (total >= 0),
  available  integer NOT NULL CHECK (available >= 0 AND available <= total),
  price      numeric(10,2) NOT NULL CHECK (price >= 0),
  PRIMARY KEY (flight_id, fare_class)
);

-- Only SOLD seats are materialised (7.5 billion seat rows would be absurd). The seat map is layout minus these rows.
-- PRIMARY KEY (flight_id, seat_no) means two buyers can never both insert the same seat.
CREATE TABLE IF NOT EXISTS seats (
  flight_id  bigint NOT NULL,
  seat_no    text   NOT NULL,
  fare_class text   NOT NULL,
  pnr        text   NOT NULL,
  user_id    bigint NOT NULL,
  PRIMARY KEY (flight_id, seat_no)
);

CREATE TABLE IF NOT EXISTS bookings (
  flight_id        bigint NOT NULL,
  pnr              text   NOT NULL,
  user_id          bigint NOT NULL,
  status           text   NOT NULL CHECK (status IN ('CONFIRMED','CANCELLED')),
  total_price      numeric(12,2) NOT NULL,
  idempotency_key  text   NOT NULL,
  created_at       timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (flight_id, pnr),
  UNIQUE (flight_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS tickets (
  flight_id      bigint NOT NULL,
  ticket_no      text   NOT NULL,
  pnr            text   NOT NULL,
  seat_no        text   NOT NULL,
  fare_class     text   NOT NULL,
  passenger_name text   NOT NULL,
  price          numeric(10,2) NOT NULL,
  PRIMARY KEY (flight_id, ticket_no)
);

-- Transactional outbox: written in the SAME transaction as the booking, drained by workers/outbox_worker.py.
CREATE TABLE IF NOT EXISTS outbox (
  flight_id    bigint NOT NULL,
  id           bigint GENERATED ALWAYS AS IDENTITY,
  event_type   text   NOT NULL,
  payload      jsonb  NOT NULL,
  created_at   timestamptz NOT NULL DEFAULT now(),
  processed_at timestamptz,
  PRIMARY KEY (flight_id, id)
);
