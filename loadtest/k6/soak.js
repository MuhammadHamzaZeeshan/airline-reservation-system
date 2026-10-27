// Soak: steady 200 users for SOAK_MINUTES (default 10). Watch Grafana for latency drift / pool leaks.
import http from 'k6/http';
import { check, sleep } from 'k6';
import { searchUrl } from './common.js';

export const options = {
  stages: [{ duration: '30s', target: 200 }, { duration: `${__ENV.SOAK_MINUTES || 10}m`, target: 200 }, { duration: '20s', target: 0 }],
  thresholds: { 'http_req_duration{name:search}': ['p(95)<300'], http_req_failed: ['rate<0.02'] },
};
export default function () {
  check(http.get(searchUrl(), { tags: { name: 'search' } }), { ok: (x) => x.status === 200 || x.status === 429 });
  sleep(0.5 + Math.random());
}
