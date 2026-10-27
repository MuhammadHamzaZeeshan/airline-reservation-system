// Baseline: 500 concurrent users searching. Target (N-2): search p95 < 300 ms, errors < 2%.
import http from 'k6/http';
import { check, sleep } from 'k6';
import { searchUrl } from './common.js';

export const options = {
  stages: [{ duration: '30s', target: 500 }, { duration: '60s', target: 500 }, { duration: '15s', target: 0 }],
  thresholds: {
    'http_req_duration{name:search}': ['p(95)<300'],
    http_req_failed: ['rate<0.02'],
  },
};

export default function () {
  const r = http.get(searchUrl(), { tags: { name: 'search' } });
  check(r, { 'status 200 or shed(429)': (x) => x.status === 200 || x.status === 429 });
  sleep(0.3 + Math.random() * 0.7);
}
