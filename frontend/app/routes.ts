import { type RouteConfig, index, route } from "@react-router/dev/routes";

export default [
  index("routes/home.tsx"),
  route("results/:reportId", "routes/results.tsx"),
  route("full-audit", "routes/full-audit.tsx"),
  route("full-audit/:auditId", "routes/full-audit.$auditId.tsx"),
  route("revenue-leak/:auditId", "routes/revenue-leak.$auditId.tsx"),
] satisfies RouteConfig;
