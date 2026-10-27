-- Every row must show 0. Used after race tests, k6 booking storms and chaos runs.
SELECT 'negative_inventory' AS check, count(*) FROM seat_inventory WHERE available < 0
UNION ALL SELECT 'double_booked_seats', count(*) FROM (SELECT flight_id, seat_no FROM seats GROUP BY 1,2 HAVING count(*) > 1) x
UNION ALL SELECT 'inventory_vs_seats_mismatch_demo_flights', count(*) FROM seat_inventory si
  WHERE si.flight_id > 900000000 AND si.total - si.available <> (SELECT count(*) FROM seats s WHERE s.flight_id = si.flight_id AND s.fare_class = si.fare_class)
UNION ALL SELECT 'seats_left_mismatch_demo_flights', count(*) FROM flights f
  WHERE f.flight_id > 900000000 AND f.seats_left <> (SELECT coalesce(sum(available),0) FROM seat_inventory si WHERE si.flight_id = f.flight_id);
