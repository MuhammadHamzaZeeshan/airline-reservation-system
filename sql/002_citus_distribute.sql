-- 002_citus_distribute.sql : run ONLY on the Citus coordinator (after workers are registered).
-- Idempotent: skips tables that are already distributed.
SET citus.shard_count = 32;            -- 32 shards over N workers: room to rebalance when workers are added
SET citus.shard_replication_factor = 1; -- durability comes from streaming replicas, not Citus statement replication

DO $$
DECLARE t text;
BEGIN
  -- reference tables: full copy on every node, so joins never cross the network
  FOREACH t IN ARRAY ARRAY['airports','airlines','aircraft_types','routes'] LOOP
    IF NOT EXISTS (SELECT 1 FROM pg_dist_partition WHERE logicalrelid = t::regclass) THEN
      PERFORM create_reference_table(t);
    END IF;
  END LOOP;

  -- users spread evenly by user_id
  IF NOT EXISTS (SELECT 1 FROM pg_dist_partition WHERE logicalrelid = 'users'::regclass) THEN
    PERFORM create_distributed_table('users', 'user_id');
  END IF;
  -- uniqueness registries: shard key == the unique value, so each check/insert touches exactly one shard
  IF NOT EXISTS (SELECT 1 FROM pg_dist_partition WHERE logicalrelid = 'username_registry'::regclass) THEN
    PERFORM create_distributed_table('username_registry', 'username', colocate_with => 'none');
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_dist_partition WHERE logicalrelid = 'email_registry'::regclass) THEN
    PERFORM create_distributed_table('email_registry', 'email', colocate_with => 'none');
  END IF;

  -- flight-keyed tables: co-located so a booking (seats+inventory+booking+tickets+outbox) is ONE shard = single-node ACID
  IF NOT EXISTS (SELECT 1 FROM pg_dist_partition WHERE logicalrelid = 'flights'::regclass) THEN
    PERFORM create_distributed_table('flights', 'flight_id', colocate_with => 'none');
  END IF;
  FOREACH t IN ARRAY ARRAY['seat_inventory','seats','bookings','tickets','outbox'] LOOP
    IF NOT EXISTS (SELECT 1 FROM pg_dist_partition WHERE logicalrelid = t::regclass) THEN
      PERFORM create_distributed_table(t, 'flight_id', colocate_with => 'flights');
    END IF;
  END LOOP;
END $$;

SELECT logicalrelid::text AS table_name, partmethod, colocationid FROM pg_dist_partition ORDER BY colocationid, 1;
