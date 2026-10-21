import type { AssignableUser } from "./types";
import { http } from "./http";

export const usersApi = {
  listAssignableUsers: (factoryId: string) =>
    http<AssignableUser[]>(
      `/api/v1/users/assignable?factory_id=${encodeURIComponent(factoryId)}`
    )
};
