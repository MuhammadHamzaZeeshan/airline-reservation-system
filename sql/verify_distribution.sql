-- Run: make verify-distribution   (Citus coordinator only)
\echo '--- worker nodes ---'
SELECT nodeid, nodename, nodeport, noderole, isactive FROM pg_dist_node ORDER BY nodeid;
\echo '--- distributed tables ---'
SELECT table_name, citus_table_type, distribution_column, colocation_id, shard_count, pg_size_pretty(table_size) AS size
FROM citus_tables ORDER BY colocation_id, table_name;
\echo '--- shards per worker (flights) ---'
SELECT nodename, count(*) AS shards, pg_size_pretty(sum(shard_size)) AS size
FROM citus_shards WHERE table_name = 'flights'::regclass GROUP BY nodename ORDER BY nodename;
\echo '--- flights row estimate per worker ---'
SELECT s.nodename, sum(greatest((r.result)::bigint,0)) AS est_rows
FROM run_command_on_shards('flights', $$SELECT reltuples::bigint FROM pg_class WHERE oid = '%s'::regclass$$) r
JOIN citus_shards s ON s.shardid = r.shardid AND s.table_name = 'flights'::regclass
GROUP BY s.nodename ORDER BY s.nodename;
\echo '--- co-location check (all must share one colocation_id) ---'
SELECT colocation_id, string_agg(table_name::text, ', ' ORDER BY table_name) FROM citus_tables
WHERE table_name::text IN ('flights','seat_inventory','seats','bookings','tickets','outbox') GROUP BY colocation_id;
