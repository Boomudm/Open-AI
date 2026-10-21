import type {
  AdminUserBrief,
  AdminUserCreate,
  AdminUserUpdate,
  ApiKeyCreate,
  ApiKeyCreated,
  ApiKeyOut,
  ExternalConnectionTestResult,
  ExternalDataSourceCreate,
  ExternalDataSourceOut,
  ExternalDiscoveredTable,
  FactoryAdmin,
  FactoryCreate,
  FactorySettingsPatch,
  FactorySettingsResponse,
  JobPositionAdmin,
  JobPositionCreate,
  JobPositionUpdate,
  JobPositionUsage,
  PaginatedResponse,
} from "./types";
import { http } from "./http";

export const adminApi = {
  adminListUsers: (params?: { page?: number; page_size?: number }) => {
    const qs = new URLSearchParams();
    if (params?.page) qs.set("page", String(params.page));
    if (params?.page_size) qs.set("page_size", String(params.page_size));
    const query = qs.toString();
    return http<PaginatedResponse<AdminUserBrief>>(
      `/api/v1/admin/users${query ? `?${query}` : ""}`
    );
  },

  adminCreateUser: (body: AdminUserCreate) =>
    http<AdminUserBrief>("/api/v1/admin/users", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  adminListFactories: () => http<FactoryAdmin[]>("/api/v1/admin/factories"),

  adminCreateFactory: (body: FactoryCreate) =>
    http<FactoryAdmin>("/api/v1/admin/factories", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  adminDeleteFactory: (factoryId: string) =>
    http<void>(`/api/v1/admin/factories/${encodeURIComponent(factoryId)}`, {
      method: "DELETE",
    }),

  adminGetFactorySettings: (factoryId: string) =>
    http<FactorySettingsResponse>(`/api/v1/admin/factories/${encodeURIComponent(factoryId)}/settings`),

  adminPatchFactorySettings: (factoryId: string, body: FactorySettingsPatch) =>
    http<FactorySettingsResponse>(`/api/v1/admin/factories/${encodeURIComponent(factoryId)}/settings`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  adminUpdateUser: (userId: string, body: AdminUserUpdate) =>
    http<AdminUserBrief>(`/api/v1/admin/users/${userId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  adminPromoteOperator: (userId: string) =>
    http<AdminUserBrief>(`/api/v1/admin/users/${userId}/promote-operator`, {
      method: "POST",
    }),

  adminListApiKeys: () => http<ApiKeyOut[]>("/api/v1/admin/api-keys"),

  adminCreateApiKey: (body: ApiKeyCreate) =>
    http<ApiKeyCreated>("/api/v1/admin/api-keys", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  adminRevokeApiKey: (keyId: string) =>
    http<ApiKeyOut>(`/api/v1/admin/api-keys/${keyId}/revoke`, { method: "POST" }),

  adminDeleteApiKey: (keyId: string) =>
    http<void>(`/api/v1/admin/api-keys/${keyId}`, { method: "DELETE" }),

  adminListJobPositions: () => http<JobPositionAdmin[]>("/api/v1/admin/job-positions"),

  adminCreateJobPosition: (body: JobPositionCreate) =>
    http<JobPositionAdmin>("/api/v1/admin/job-positions", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  adminUpdateJobPosition: (positionId: string, body: JobPositionUpdate) =>
    http<JobPositionAdmin>(`/api/v1/admin/job-positions/${positionId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  adminJobPositionUsage: (positionId: string) =>
    http<JobPositionUsage>(`/api/v1/admin/job-positions/${positionId}/usage`),

  adminListDataSources: () => http<ExternalDataSourceOut[]>("/api/v1/admin/data-sources"),

  adminCreateDataSource: (body: ExternalDataSourceCreate) =>
    http<ExternalDataSourceOut>("/api/v1/admin/data-sources", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  adminUpdateDataSource: (sourceId: string, body: Partial<ExternalDataSourceCreate> & { is_enabled?: boolean }) =>
    http<ExternalDataSourceOut>(`/api/v1/admin/data-sources/${sourceId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  adminDeleteDataSource: (sourceId: string) =>
    http<void>(`/api/v1/admin/data-sources/${sourceId}`, { method: "DELETE" }),

  adminTestDataSource: (sourceId: string) =>
    http<ExternalConnectionTestResult>(`/api/v1/admin/data-sources/${sourceId}/test`, {
      method: "POST",
    }),

  /** Test raw connection params from the create-form, before anything is saved. */
  adminTestConnectionParams: (body: {
    host: string;
    port: number;
    database_name: string;
    username: string;
    password: string;
    ssl_mode: string;
  }) =>
    http<ExternalConnectionTestResult>("/api/v1/admin/data-sources/test", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  adminDiscoverDataSourceTables: (sourceId: string) =>
    http<ExternalDiscoveredTable[]>(`/api/v1/admin/data-sources/${sourceId}/discover`),

  adminSetDataSourceTables: (
    sourceId: string,
    tables: Array<{
      schema_name: string;
      table_name: string;
      description?: string | null;
      columns_meta?: ExternalDiscoveredTable["columns"];
      factory_ids?: string[];
      position_ids?: string[];
    }>
  ) =>
    http<ExternalDataSourceOut>(`/api/v1/admin/data-sources/${sourceId}/tables`, {
      method: "PUT",
      body: JSON.stringify({ tables }),
    }),
};
