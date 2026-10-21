import type { FactoryBrief } from "./types";
import { http } from "./http";

export const factoriesApi = {
  listFactories: () => http<FactoryBrief[]>("/api/v1/factories")
};
