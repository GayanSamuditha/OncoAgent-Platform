import http from "k6/http";
import { check } from "k6";

export const correlationPrefix = __ENV.CORRELATION_PREFIX || "loadtest-";

export function login(baseUrl, identity) {
  const response = http.post(
    `${baseUrl}/backend/api/v1/auth/login`,
    JSON.stringify({ user_key: identity }),
    {
      headers: {
        "content-type": "application/json",
        "x-correlation-id": `${correlationPrefix}login`,
      },
      tags: { name: "POST /backend/api/v1/auth/login" },
    },
  );
  return check(response, { "local login succeeded": (item) => item.status === 200 });
}

export function getJson(baseUrl, path, name) {
  return http.get(`${baseUrl}${path}`, {
    headers: { "x-correlation-id": `${correlationPrefix}read` },
    tags: { name },
  });
}

export function summaryOutput(data) {
  const path = __ENV.REPORT_PATH || "/reports/k6-summary.json";
  return { [path]: JSON.stringify(data, null, 2) };
}
