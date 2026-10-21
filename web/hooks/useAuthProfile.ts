"use client";

import { useQuery, useQueryClient, type UseQueryResult } from "@tanstack/react-query";
import { useCallback } from "react";
import type { UserProfile } from "@/lib/api";
import {
  canAccessFactory,
  canUploadDocuments,
  canWriteFactory,
  getAuthProfile,
  getEffectiveRole,
  getJobPositionIds,
  handleUnauthorized,
  hasNoJobPositionAssigned,
  isAdminUser,
  isAuthenticated as isAuthCached,
  needsPrivacyAcceptance,
  setAuthProfile,
  type AccessLevel,
} from "@/lib/auth";
import { STALE_STATIC } from "@/lib/query-config";
import { queryKeys } from "@/lib/query-keys";

async function fetchAuthProfile(): Promise<UserProfile | null> {
  const res = await fetch("/api/v1/auth/me", {
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
  });
  if (res.status === 401) {
    setAuthProfile(null);
    try {
      await fetch("/api/auth/session", { method: "DELETE" });
    } catch {
      /* best-effort cookie clear */
    }
    return null;
  }
  if (!res.ok) {
    const cached = getAuthProfile();
    if (cached) return cached;
    throw new Error(`Failed to load profile (${res.status})`);
  }
  const profile = (await res.json()) as UserProfile;
  setAuthProfile(profile);
  return profile;
}

export type AuthProfileState = UseQueryResult<UserProfile | null, Error> & {
  profile: UserProfile | null;
  isAuthenticated: boolean;
  needsPrivacy: boolean;
  isAdmin: boolean;
  canWrite: (factoryId?: string | null) => boolean;
  canUpload: (factoryId?: string | null) => boolean;
  canAccess: (factoryId?: string | null, level?: AccessLevel) => boolean;
  jobPositionIds: string[];
  missingJobPosition: boolean;
  role: ReturnType<typeof getEffectiveRole>;
  invalidate: () => Promise<void>;
};

/** Single source of truth for authenticated user state (React Query + module cache). */
export function useAuthProfile(): AuthProfileState {
  const queryClient = useQueryClient();
  const cachedProfile = getAuthProfile();
  const query = useQuery({
    queryKey: queryKeys.myProfile(),
    queryFn: fetchAuthProfile,
    staleTime: STALE_STATIC,
    retry: 1,
    ...(cachedProfile
      ? { initialData: cachedProfile, initialDataUpdatedAt: Date.now() }
      : {}),
  });

  const profile = query.data ?? null;
  const invalidate = useCallback(async () => {
    await queryClient.invalidateQueries({ queryKey: queryKeys.myProfile() });
  }, [queryClient]);

  return {
    ...query,
    profile,
    isAuthenticated: !!profile || isAuthCached(),
    needsPrivacy: profile ? needsPrivacyAcceptance() : false,
    isAdmin: isAdminUser(),
    canWrite: (factoryId) => canWriteFactory(factoryId),
    canUpload: (factoryId) => canUploadDocuments(factoryId),
    canAccess: (factoryId, level = "read") => canAccessFactory(factoryId, level),
    jobPositionIds: getJobPositionIds(),
    missingJobPosition: hasNoJobPositionAssigned(),
    role: getEffectiveRole(),
    invalidate,
  };
}

export async function refreshAuthProfileQuery(
  queryClient: ReturnType<typeof useQueryClient>
): Promise<UserProfile | null> {
  const profile = await fetchAuthProfile();
  queryClient.setQueryData(queryKeys.myProfile(), profile);
  if (!profile && typeof window !== "undefined") {
    handleUnauthorized();
  }
  return profile;
}
