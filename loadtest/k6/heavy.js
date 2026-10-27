// Heavy load (N-3): ramp to 5,000 concurrent users. No crash, non-429 error rate < 2%, excess shed with HTTP 429.
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Counter } from 'k6/metrics';
import { BASE, searchUrl, pick } from './common.js';

const shed = new Counter('shed_429');
export const options = {
  stages: [{ duration: '30s', target: 1000 }, { duration: '30s', target: 3000 }, { duration: '30s', target: 5000 },
           { duration: '60s', target: 5000 }, { duration: '20s', target: 0 }],
  thresholds: { http_req_failed: ['rate<0.02'], checks: ['rate>0.98'] },
  noConnectionReuse: false,
};

export default function () {
  const x = Math.random();
  let r;
  if (x < 0.7) r = http.get(searchUrl(), { tags: { name: 'search' } });
  else if (x < 0.9) r = http.get(`${BASE}/v1/flights/${900000001 + Math.floor(Math.random() * 5)}/availability`, { tags: { name: 'availability' } });
  else r = http.get(`${BASE}/health/live`, { tags: { name: 'live' } });
  if (r.status === 429) shed.add(1);
  check(r, { 'served or shed (never 5xx)': (q) => q.status < 500 });
  sleep(0.5 + Math.random());
}
