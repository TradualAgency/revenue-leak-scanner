import { type RouteConfig, index, route } from "@react-router/dev/routes";

export default [
  index("routes/home.tsx"),
  route("results/:reportId", "routes/results.tsx"),
  // Operator routes are English-pathed; prospect-facing ones are Dutch.
  route("scans", "routes/scans.tsx"),
  route("full-audit", "routes/full-audit.tsx"),
  route("full-audit/:auditId", "routes/full-audit.$auditId.tsx"),
  route("revenue-leak/:auditId", "routes/revenue-leak.$auditId.tsx"),
  route("marktvergelijking/:runId", "routes/marktvergelijking.$runId.tsx"),
] satisfies RouteConfig;
