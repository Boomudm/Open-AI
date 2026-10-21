import type { LoginResponse, UserProfile, UserProfileUpdate, ChangePasswordRequest, JobPositionBrief } from "./types";
import { http } from "./http";
import { parseApiError } from "@/lib/errors";

export const authApi = {
  login: (username: string, password: string) =>
    http<LoginResponse>("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
      skipAuth: true,
      skipAuthRedirect: true,
    }),

  acceptPrivacyPolicy: () =>
    http<LoginResponse>("/api/v1/auth/privacy-acceptance", {
      method: "POST",
      skipAuthRedirect: true,
    }),

  setMyJobPosition: (positionId: string) =>
    http<LoginResponse>("/api/v1/auth/job-position", {
      method: "POST",
      body: JSON.stringify({ position_id: positionId }),
      skipAuthRedirect: true,
    }),

  getMyProfile: () => http<UserProfile>("/api/v1/auth/me"),

  updateMyProfile: (body: UserProfileUpdate) =>
    http<LoginResponse>("/api/v1/auth/me", {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  changePassword: (body: ChangePasswordRequest) =>
    http<LoginResponse>("/api/v1/auth/change-password", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  uploadProfilePicture: async (file: File) => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch("/api/v1/auth/me/profile-picture", {
      method: "POST",
      credentials: "same-origin",
      body: form,
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(parseApiError(new Error(`${res.status} ${text}`)));
    }
    return res.json() as Promise<LoginResponse>;
  },

  deleteProfilePicture: () =>
    http<LoginResponse>("/api/v1/auth/me/profile-picture", {
      method: "DELETE",
    }),

  refreshAuthToken: () =>
    http<LoginResponse>("/api/v1/auth/refresh", { method: "POST" }),

  listJobPositions: () => http<JobPositionBrief[]>("/api/v1/job-positions")
};
