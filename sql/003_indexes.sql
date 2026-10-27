-- 003_indexes.sql : built AFTER seeding (bulk load is much faster without secondary indexes).
-- Plain CREATE INDEX (not CONCURRENTLY) so the same file runs on Citus and vanilla PostgreSQL.

-- route + date: the mandatory shape of every search
CREATE INDEX IF NOT EXISTS flights_route_dep_idx   ON flights (origin_id, dest_id, departure_ts, flight_id);
CREATE INDEX IF NOT EXISTS flights_dep_idx         ON flights (departure_ts, flight_id);
-- numeric sort / filter keys (flight_id is the keyset tie-breaker)
CREATE INDEX IF NOT EXISTS flights_price_idx       ON flights (price, flight_id);
CREATE INDEX IF NOT EXISTS flights_duration_idx    ON flights (duration_min, flight_id);
CREATE INDEX IF NOT EXISTS flights_arrival_idx     ON flights (arrival_ts, flight_id);
-- partial index: only flights that still have seats
CREATE INDEX IF NOT EXISTS flights_avail_idx       ON flights (origin_id, dest_id, departure_ts) WHERE seats_left > 0;
-- text: fuzzy flight number + airport/city names
CREATE INDEX IF NOT EXISTS flights_flightno_trgm   ON flights USING gin (flight_no gin_trgm_ops);
CREATE INDEX IF NOT EXISTS airports_name_trgm      ON airports USING gin (name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS airports_city_trgm      ON airports USING gin (city gin_trgm_ops);
CREATE INDEX IF NOT EXISTS airlines_name_trgm      ON airlines USING gin (name gin_trgm_ops);
-- my bookings (fans out to all shards but is an index scan on each)
CREATE INDEX IF NOT EXISTS bookings_user_idx       ON bookings (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS tickets_pnr_idx         ON tickets (flight_id, pnr);
CREATE INDEX IF NOT EXISTS seats_pnr_idx           ON seats (flight_id, pnr);
-- outbox drain
CREATE INDEX IF NOT EXISTS outbox_pending_idx      ON outbox (id) WHERE processed_at IS NULL;
-- vector similarity (cosine). Similar-flight queries additionally restrict by route, so they stay exact and fast.
CREATE INDEX IF NOT EXISTS flights_embedding_hnsw  ON flights USING hnsw (embedding vector_cosine_ops);

ANALYZE;
