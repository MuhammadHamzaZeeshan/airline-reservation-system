CREATE DATABASE IF NOT EXISTS ars;
CREATE TABLE IF NOT EXISTS ars.booking_events (
  event_id   UInt64,
  ts         DateTime,
  event_type LowCardinality(String),
  flight_id  UInt64,
  pnr        String,
  user_id    UInt64,
  origin_id  UInt32,
  dest_id    UInt32,
  seats      UInt16,
  amount     Float64
) ENGINE = ReplacingMergeTree
PARTITION BY toYYYYMM(ts)
ORDER BY event_id;
CREATE TABLE IF NOT EXISTS ars.routes_dim (route_id UInt32, origin_id UInt32, dest_id UInt32) ENGINE = ReplacingMergeTree ORDER BY route_id;
