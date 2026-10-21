const keyWithParams = <K extends string>(key: K, params?: Record<string, unknown>) =>
  params === undefined ? ([key] as const) : ([key, params] as const);

const keyWithNestedParams = <A extends string, B extends string>(
  a: A,
  b: B,
  params?: Record<string, unknown>
) => (params === undefined ? ([a, b] as const) : ([a, b, params] as const));

export const queryKeys = {
  machines: (params?: Record<string, unknown>) => keyWithParams("machines", params),
  atRisk: (params?: Record<string, unknown>) => keyWithParams("atRisk", params),
  incidents: () => ["incidents"] as const,
  repairs: (params?: Record<string, unknown>) => keyWithParams("repairs", params),
  spareParts: (params?: Record<string, unknown>) => keyWithParams("spareParts", params),
  inventoryInsights: (params?: Record<string, unknown>) =>
    keyWithParams("inventoryInsights", params),
  inventoryStockValue: (params?: Record<string, unknown>) =>
    keyWithParams("inventoryStockValue", params),
  alerts: (params?: Record<string, unknown>) => keyWithParams("alerts", params),
  chatSessions: (params?: Record<string, unknown>) =>
    keyWithParams("chatSessions", params),
  chatCapabilities: () => ["chatCapabilities"] as const,
  chatMessages: (sessionId?: string) =>
    sessionId === undefined
      ? (["chatMessages"] as const)
      : (["chatMessages", sessionId] as const),
  documentTypes: () => ["documentTypes"] as const,
  ingestJobs: (params?: Record<string, unknown>) => keyWithParams("ingestJobs", params),
  jobPositions: () => ["jobPositions"] as const,
  myProfile: () => ["myProfile"] as const,
  adminUsers: (params?: Record<string, unknown>) => keyWithParams("adminUsers", params),
  adminFactories: () => ["adminFactories"] as const,
  adminFactorySettings: (factoryId: string) => ["adminFactorySettings", factoryId] as const,
  adminJobPositions: () => ["adminJobPositions"] as const,
  adminApiKeys: () => ["adminApiKeys"] as const,
  adminDataSources: () => ["adminDataSources"] as const,
  documents: (params?: Record<string, unknown>) => keyWithParams("documents", params),
  documentPolicyFindings: (docId: string) => ["documentPolicyFindings", docId] as const,
  factories: () => ["factories"] as const,
  handover: (factoryId?: string | null, hoursBack?: number) =>
    ["handover", factoryId, hoursBack] as const,
  observabilityOverview: () => ["observability", "overview"] as const,
  systemAdminDashboard: () => ["systemAdmin", "dashboard"] as const,
  insightsPulse: (params?: Record<string, unknown>) =>
    keyWithNestedParams("insights", "pulse", params),
  insightsAiTrends: (params?: Record<string, unknown>) =>
    keyWithNestedParams("insights", "aiTrends", params),
  insightsSymptoms: (params?: Record<string, unknown>) =>
    keyWithNestedParams("insights", "symptoms", params),
  insightsHeatmap: (params?: Record<string, unknown>) =>
    keyWithNestedParams("insights", "heatmap", params),
  insightsFeedbackGaps: (params?: Record<string, unknown>) =>
    keyWithNestedParams("insights", "feedbackGaps", params),
  insightsQualityFailures: (params?: Record<string, unknown>) =>
    keyWithNestedParams("insights", "qualityFailures", params),
  insightsDrilldown: (params?: Record<string, unknown>) =>
    keyWithNestedParams("insights", "drilldown", params),
  insightsBucketMeta: (params?: Record<string, unknown>) =>
    keyWithNestedParams("insights", "bucketMeta", params),
  insightsFactoryBenchmark: (params?: Record<string, unknown>) =>
    keyWithNestedParams("insights", "factoryBenchmark", params),
  insightsCorrelationHints: (params?: Record<string, unknown>) =>
    keyWithNestedParams("insights", "correlationHints", params),
  inventoryReport: (reportId: string | null) => ["inventoryReport", reportId] as const,
} as const;
