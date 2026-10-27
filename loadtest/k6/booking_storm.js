// Booking storm: 40 users fight for the few seats left on the 5 demo flights (1..5 seats each).
// Expected: 409s are normal; NO 5xx; afterwards `make verify-inventory` must report 0 double bookings and 0 negative inventory.
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Counter } from 'k6/metrics';
import { BASE, register, pick } from './common.js';

const outcome = new Counter('booking_outcome');
export const options = {
  scenarios: { storm: { executor: 'constant-vus', vus: 40, duration: '40s' } },
  thresholds: { http_req_failed: ['rate<0.02'], 'booking_outcome{result:server_error}': ['count==0'] },
};

export function setup() {
  const tokens = [];
  const run = Date.now().toString(36);
  for (let i = 0; i < 40; i++) { const t = register(`storm_${run}_${i}`); if (t) tokens.push(t); }
  return { tokens };
}

export default function (data) {
  const token = data.tokens[(__VU - 1) % data.tokens.length];
  const h = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };
  const fid = 900000001 + Math.floor(Math.random() * 5);
  const sm = http.get(`${BASE}/v1/flights/${fid}/seatmap`).json('seats');
  const free = (sm || []).filter((s) => s.status === 'available');
  if (free.length === 0) { outcome.add(1, { result: 'sold_out' }); sleep(0.2); return; }
  const seat = pick(free).seat_no;
  const hold = http.post(`${BASE}/v1/holds`, JSON.stringify({ flight_id: fid, seats: [seat] }), { headers: h });
  if (hold.status >= 500) { outcome.add(1, { result: 'server_error' }); return; }
  if (hold.status !== 201) { outcome.add(1, { result: 'hold_conflict' }); return; }
  const key = `${__VU}-${__ITER}-${Date.now()}`;
  const b = http.post(`${BASE}/v1/bookings`, JSON.stringify({ flight_id: fid, hold_id: hold.json('hold_id'), passengers: [{ name: 'K6 Pax', seat_no: seat }] }),
                      { headers: { ...h, 'Idempotency-Key': key } });
  check(b, { 'booking never 5xx': (x) => x.status < 500 });
  outcome.add(1, { result: b.status === 201 ? 'booked' : b.status >= 500 ? 'server_error' : 'booking_conflict' });
  sleep(0.1);
}
