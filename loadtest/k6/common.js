import http from 'k6/http';

export const BASE = __ENV.BASE_URL || 'http://nginx:80';
// 429 (load shedding) is an EXPECTED, healthy answer under overload: it must not count as a failed request.
http.setResponseCallback(http.expectedStatuses({ min: 200, max: 399 }, 429, 409));

const ROUTES = [['Karachi', 'London'], ['KHI', 'DXB'], ['Lahore', 'Dubai'], ['ISB', 'LHR'], ['DXB', 'LHR'],
                ['KHI', 'JFK'], ['Karachi', 'Doha'], ['KHI', 'IST'], ['Delhi', 'Mumbai'], ['Singapore', 'Bangkok']];
const SORTS = ['price:asc', 'duration:asc', 'departure:asc', 'price:desc,duration:asc', 'seats:desc', 'arrival:asc'];

export function pick(a) { return a[Math.floor(Math.random() * a.length)]; }

export function searchUrl() {
  const [o, d] = pick(ROUTES);
  const from = new Date();
  const to = new Date(Date.now() + 90 * 86400000);
  let u = `${BASE}/v1/flights/search?origin=${encodeURIComponent(o)}&destination=${encodeURIComponent(d)}` +
          `&date_from=${from.toISOString()}&date_to=${to.toISOString()}&sort=${encodeURIComponent(pick(SORTS))}&limit=20`;
  if (Math.random() < 0.4) u += `&max_price=${300 + Math.floor(Math.random() * 600)}`;
  if (Math.random() < 0.3) u += `&max_stops=${Math.floor(Math.random() * 3)}`;
  return u;
}

export function register(name) {
  const r = http.post(`${BASE}/v1/auth/register`, JSON.stringify({ username: name, email: `${name}@k6.local`, password: 'Passw0rd!x' }),
                      { headers: { 'Content-Type': 'application/json' } });
  return r.status === 201 ? r.json('access_token') : null;
}
