import { check } from "k6";
import { sleep } from "k6";
import { getJson, login, summaryOutput } from "../helpers/common.js";

const profile = __ENV.TEST_PROFILE || "smoke";
const baseUrl = __ENV.BASE_URL || "http://web:3000";
const duration = Number(__ENV.DURATION_SECONDS || 30);
const maximumRps = Number(__ENV.MAXIMUM_RPS || 10);
const startRps = Number(__ENV.START_RPS || 5);
const recoveryRps = Number(__ENV.RECOVERY_RPS || 10);
const virtualUsers = Number(__ENV.VIRTUAL_USERS || 2);
const identities = JSON.parse(__ENV.IDENTITIES_JSON || "{}");
let authenticated = false;
let role = "administrator";
let knownRunId = "";
let knownApprovalId = "";

function scenarioOptions() {
  if (profile === "smoke") {
    return { executor: "constant-vus", vus: 2, duration: `${duration}s` };
  }
  if (profile === "baseline") {
    return {
      executor: "ramping-arrival-rate",
      startRate: startRps,
      timeUnit: "1s",
      preAllocatedVUs: Math.min(virtualUsers, 40),
      maxVUs: virtualUsers,
      stages: [{ target: maximumRps, duration: `${duration}s` }],
    };
  }
  if (profile === "burst") {
    return {
      executor: "ramping-arrival-rate",
      startRate: startRps,
      timeUnit: "1s",
      preAllocatedVUs: Math.min(virtualUsers, 80),
      maxVUs: virtualUsers,
      stages: [
        { target: maximumRps, duration: "30s" },
        { target: maximumRps, duration: "60s" },
        { target: recoveryRps, duration: "30s" },
      ],
    };
  }
  return {
    executor: "constant-arrival-rate",
    rate: maximumRps,
    timeUnit: "1s",
    duration: `${duration}s`,
    preAllocatedVUs: Math.min(virtualUsers, 50),
    maxVUs: virtualUsers,
  };
}

export const options = {
  scenarios: { api: scenarioOptions() },
  thresholds: {
    http_req_failed: [{ threshold: "rate<0.15", abortOnFail: true, delayAbortEval: "30s" }],
    http_req_duration: [{ threshold: "p(95)<10000", abortOnFail: true, delayAbortEval: "30s" }],
  },
  systemTags: ["status", "method", "name", "scenario"],
};

function ensureLogin() {
  if (authenticated) return true;
  const roles = profile === "smoke"
    ? ["administrator"]
    : ["researcher", "reviewer", "platform_operator", "administrator"];
  role = roles[(__VU - 1) % roles.length];
  const identity = identities[role];
  authenticated = Boolean(identity) && login(baseUrl, identity);
  return authenticated;
}

function checked(response, label) {
  check(response, { [`${label} succeeded`]: (item) => item.status >= 200 && item.status < 400 });
}

function smoke() {
  for (const [path, name] of [
    ["/backend/api/v1/auth/me", "GET /backend/api/v1/auth/me"],
    ["/backend/api/v1/datasets", "GET /backend/api/v1/datasets"],
    ["/backend/api/v1/agents", "GET /backend/api/v1/agents"],
    ["/backend/api/v1/evaluations", "GET /backend/api/v1/evaluations"],
    ["/backend/api/v1/performance", "GET /backend/api/v1/performance"],
    ["/backend/api/v1/resilience/certifications", "GET /backend/api/v1/resilience/certifications"],
    ["/backend/api/v1/observability/status", "GET /backend/api/v1/observability/status"],
    ["/backend/api/v1/audit-events?page_size=10", "GET /backend/api/v1/audit-events"],
  ]) checked(getJson(baseUrl, path, name), name);
}

function researcherRead() {
  const choice = Math.random();
  if (choice < 0.3) {
    checked(getJson(baseUrl, "/backend/api/v1/datasets", "GET /backend/api/v1/datasets"), "datasets");
    return;
  }
  if (choice < 0.65 || !knownRunId) {
    const runs = getJson(baseUrl, "/backend/api/v1/runs?page_size=10", "GET /backend/api/v1/runs");
    checked(runs, "runs");
    const items = runs.status === 200 ? runs.json("items") || [] : [];
    if (items.length) knownRunId = items[Math.floor(Math.random() * items.length)].run_id;
    return;
  }
  const suffix = choice < 0.82 ? "evidence" : choice < 0.94 ? "events" : "candidates";
  checked(
    getJson(
      baseUrl,
      `/backend/api/v1/runs/${knownRunId}/${suffix}`,
      `GET /backend/api/v1/runs/:run_id/${suffix}`,
    ),
    suffix,
  );
}

function reviewerRead() {
  if (knownApprovalId && Math.random() > 0.5) {
    checked(
      getJson(
        baseUrl,
        `/backend/api/v1/approvals/${knownApprovalId}`,
        "GET /backend/api/v1/approvals/:approval_id",
      ),
      "review detail",
    );
    return;
  }
  const reviews = getJson(
    baseUrl,
    "/backend/api/v1/approvals?page_size=10",
    "GET /backend/api/v1/approvals",
  );
  checked(reviews, "reviews");
  const items = reviews.status === 200 ? reviews.json("items") || [] : [];
  if (items.length) knownApprovalId = items[0].id;
}

function operatorRead() {
  const routes = [
    ["/backend/api/v1/agents", "GET /backend/api/v1/agents"],
    ["/backend/api/v1/performance", "GET /backend/api/v1/performance"],
    ["/backend/api/v1/resilience/certifications", "GET /backend/api/v1/resilience/certifications"],
    ["/backend/api/v1/observability/status", "GET /backend/api/v1/observability/status"],
  ];
  const selected = routes[Math.floor(Math.random() * routes.length)];
  checked(getJson(baseUrl, selected[0], selected[1]), selected[1]);
}

function administratorRead() {
  const routes = [
    ["/backend/api/v1/evaluations", "GET /backend/api/v1/evaluations"],
    ["/backend/api/v1/release-evaluations", "GET /backend/api/v1/release-evaluations"],
    ["/backend/api/v1/performance", "GET /backend/api/v1/performance"],
    ["/backend/api/v1/resilience/certifications", "GET /backend/api/v1/resilience/certifications"],
    ["/backend/api/v1/observability/status", "GET /backend/api/v1/observability/status"],
    ["/backend/api/v1/audit-events?page_size=10", "GET /backend/api/v1/audit-events"],
  ];
  const selected = routes[Math.floor(Math.random() * routes.length)];
  checked(getJson(baseUrl, selected[0], selected[1]), selected[1]);
}

export default function () {
  if (!ensureLogin()) return;
  if (profile === "smoke") {
    smoke();
    sleep(1);
    return;
  }
  if (role === "researcher") return researcherRead();
  if (role === "reviewer") return reviewerRead();
  if (role === "platform_operator") return operatorRead();
  return administratorRead();
}

export function handleSummary(data) {
  return summaryOutput(data);
}
