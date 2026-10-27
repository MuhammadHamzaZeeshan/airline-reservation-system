
import http from 'k6/http';
import { check } from 'k6';

const baseUrl = __ENV.BASE_URL || 'http://ars-nginx:80';

export const options = {
  scenarios: {
    exact_ten_lacs: {
      executor: 'shared-iterations',
      vus: 500,                  // Reasonable thread pool to avoid Docker freeze
      iterations: 2000000,       // Exactly 10 Lac requests
      maxDuration: '10m',        // Timeout limit
    },
  },
  thresholds: {
    'http_req_duration{name:search_endpoint}': ['p(95)<300'],
    http_req_failed: ['rate<0.01'],
  },
};

export default function () {
  const params = {
    tags: { name: 'search_endpoint' },
    headers: { 'Content-Type': 'application/json' },
  };

  const res = http.get(`${baseUrl}/`, params);

  check(res, {
    'status is 200 or 429': (r) => r.status === 200 || r.status === 429,
    'latency under 300ms': (r) => r.timings.duration < 300,
  });
}