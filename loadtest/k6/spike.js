// Spike: 50 -> 3,000 users in 10 s, hold, back down. The API must stay up and recover.
import http from 'k6/http';
import { check, sleep } from 'k6';
import { searchUrl } from './common.js';

export const options = {
  stages: [{ duration: '20s', target: 50 }, { duration: '10s', target: 3000 }, { duration: '40s', target: 3000 }, { duration: '10s', target: 50 }, { duration: '30s', target: 50 }],
  thresholds: { http_req_failed: ['rate<0.02'] },
};
export default function () {
  const r = http.get(searchUrl(), { tags: { name: 'search' } });
  check(r, { 'never 5xx': (x) => x.status < 500 });
  sleep(0.2 + Math.random() * 0.5);
}
