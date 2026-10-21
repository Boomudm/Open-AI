import type { ObservabilityOverview } from "./types";
import { http } from "./http";

export const observabilityApi = {
  observabilityOverview: (rangeMinutes = 60) =>
    http<ObservabilityOverview>(
      `/api/v1/observability/overview?range_minutes=${rangeMinutes}`
    )
};
