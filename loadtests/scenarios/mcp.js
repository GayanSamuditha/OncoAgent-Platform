import http from "k6/http";
import { check } from "k6";
import { summaryOutput } from "../helpers/common.js";

const baseUrl = __ENV.MCP_URL || "http://mcp:8010/mcp";
const datasetId = __ENV.DATASET_ID;
const clientId = __ENV.MCP_CLIENT_ID;
const token = __ENV.MCP_TOKEN;
const duration = Number(__ENV.DURATION_SECONDS || 180);
const maximumRps = Number(__ENV.MAXIMUM_RPS || 30);
const virtualUsers = Number(__ENV.VIRTUAL_USERS || 40);
let sessionId = "";
let patientId = "";
let requestSequence = 1;

export const options = {
  scenarios: {
    mcp: {
      executor: "ramping-arrival-rate",
      startRate: 1,
      timeUnit: "1s",
      preAllocatedVUs: Math.min(virtualUsers, 30),
      maxVUs: virtualUsers,
      stages: [{ target: maximumRps, duration: `${duration}s` }],
    },
  },
  thresholds: {
    http_req_failed: [{ threshold: "rate<0.15", abortOnFail: true, delayAbortEval: "30s" }],
    http_req_duration: [{ threshold: "p(95)<10000", abortOnFail: true, delayAbortEval: "30s" }],
  },
  systemTags: ["status", "method", "name", "scenario"],
};

function headers(extra = {}) {
  return {
    accept: "application/json, text/event-stream",
    "content-type": "application/json",
    "x-mcp-client-id": clientId,
    authorization: `Bearer ${token}`,
    "x-correlation-id": "loadtest-mcp",
    ...extra,
  };
}

function rpc(method, params, name) {
  const id = requestSequence++;
  const response = http.post(
    baseUrl,
    JSON.stringify({ jsonrpc: "2.0", id, method, params }),
    {
      headers: headers(sessionId ? { "mcp-session-id": sessionId } : {}),
      tags: { name },
    },
  );
  return response;
}

function parseRpc(response) {
  const lines = response.body.split("\n");
  const data = lines.find((line) => line.startsWith("data: "));
  if (!data) return {};
  try {
    return JSON.parse(data.slice(6));
  } catch {
    return {};
  }
}

function initialize() {
  const response = rpc(
    "initialize",
    {
      protocolVersion: "2025-06-18",
      capabilities: {},
      clientInfo: { name: "oncoagent-loadtest", version: "1" },
    },
    "MCP initialize",
  );
  sessionId = response.headers["Mcp-Session-Id"] || response.headers["mcp-session-id"] || "";
  return check(response, {
    "MCP initialized": (item) => item.status === 200 && Boolean(sessionId),
  });
}

function callTool(tool, request) {
  const response = rpc(
    "tools/call",
    { name: tool, arguments: { request } },
    `MCP ${tool}`,
  );
  const payload = parseRpc(response);
  check(response, {
    "MCP transport succeeded": (item) => item.status === 200,
    "MCP tool succeeded": () => !payload.error && payload.result?.isError !== true,
  });
  return payload;
}

function extractPatient(payload) {
  const structured = payload.result?.structuredContent || {};
  const items = structured.items || [];
  if (items.length) return items[0].patient_id || items[0].metadata?.patient_id || "";
  const text = payload.result?.content?.[0]?.text;
  if (!text) return "";
  try {
    const parsed = JSON.parse(text);
    return parsed.items?.[0]?.patient_id || parsed.items?.[0]?.metadata?.patient_id || "";
  } catch {
    return "";
  }
}

export default function () {
  if (!sessionId && !initialize()) return;
  if (!patientId) {
    const search = callTool("search_clinical_documents", {
      dataset_id: datasetId,
      query: "diabetes hypertension",
      top_k: 5,
      retrieval_profile: "postgres_fts",
    });
    patientId = extractPatient(search);
    return;
  }
  const tools = [
    "get_patient_demographics",
    "get_patient_conditions",
    "get_patient_observations",
    "get_patient_procedures",
    "get_patient_medications",
    "get_patient_diagnostic_reports",
    "get_patient_encounters",
    "build_patient_evidence",
  ];
  const tool = tools[(__ITER + __VU) % tools.length];
  callTool(tool, { dataset_id: datasetId, patient_id: patientId });
}

export function handleSummary(data) {
  return summaryOutput(data);
}
