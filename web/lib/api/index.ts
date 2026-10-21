/** Domain-split API client — import from `@/lib/api` or `@/lib/api/<domain>`. */
export * from "./types";
export { http, type HttpOptions } from "./http";
export { authApi } from "./auth";
export { factoriesApi } from "./factories";
export { machinesApi } from "./machines";
export { documentsApi } from "./documents";
export { chatApi } from "./chat";
export { ingestApi } from "./ingest";
export { alertsApi } from "./alerts";
export { analyticsApi } from "./analytics";
export { insightsApi } from "./insights";
export { feedbackApi } from "./feedback";
export { handoverApi } from "./handover";
export { rcaApi } from "./rca";
export { observabilityApi } from "./observability";
export { usersApi } from "./users";
export { adminApi } from "./admin";
export { systemAdminApi } from "./systemAdmin";

import { authApi } from "./auth";
import { factoriesApi } from "./factories";
import { machinesApi } from "./machines";
import { documentsApi } from "./documents";
import { chatApi } from "./chat";
import { ingestApi } from "./ingest";
import { alertsApi } from "./alerts";
import { analyticsApi } from "./analytics";
import { insightsApi } from "./insights";
import { feedbackApi } from "./feedback";
import { handoverApi } from "./handover";
import { rcaApi } from "./rca";
import { observabilityApi } from "./observability";
import { usersApi } from "./users";
import { adminApi } from "./admin";
import { systemAdminApi } from "./systemAdmin";

/** Unified API facade (backward compatible). */
export const api = {
  ...authApi,
  ...factoriesApi,
  ...machinesApi,
  ...documentsApi,
  ...chatApi,
  ...ingestApi,
  ...alertsApi,
  ...analyticsApi,
  ...insightsApi,
  ...feedbackApi,
  ...handoverApi,
  ...rcaApi,
  ...observabilityApi,
  ...usersApi,
  ...adminApi,
  ...systemAdminApi,
};
