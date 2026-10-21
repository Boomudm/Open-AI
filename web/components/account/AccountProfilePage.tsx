"use client";

import { api, type UserProfile } from "@/lib/api";
import {
  getPostLoginPath,
  getUsername,
  isAdminUser,
  persistLogin,
  roleDisplayLabel,
} from "@/lib/auth";
import { cn } from "@/lib/cn";
import { parseApiError } from "@/lib/errors";
import { queryKeys } from "@/lib/query-keys";
import { resolveUserEmail, userInitials } from "@/lib/userDisplay";
import { useJobPositions } from "@/hooks/useJobPositions";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Building2, Camera, KeyRound, Loader2, Shield, Trash2, Upload, UserRound } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState, type ReactNode } from "react";

const ACCESS_LABELS: Record<string, string> = {
  read: "อ่าน",
  write: "เขียน",
  admin: "ผู้ดูแล",
};
const PROFILE_IMAGE_MAX_BYTES = 2 * 1024 * 1024;
const PROFILE_IMAGE_TYPES = new Set(["image/jpeg", "image/png", "image/webp"]);

export function AccountProfilePage() {
  const queryClient = useQueryClient();
  const { data: profile, isLoading, error } = useQuery({
    queryKey: queryKeys.myProfile(),
    queryFn: () => api.getMyProfile(),
  });
  const { data: jobPositions = [] } = useJobPositions();

  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [jobPositionId, setJobPositionId] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [profileMessage, setProfileMessage] = useState("");
  const [passwordMessage, setPasswordMessage] = useState("");
  const [formError, setFormError] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!profile) return;
    setFullName(profile.full_name ?? "");
    setEmail(profile.email ?? "");
    setJobPositionId(profile.job_positions[0]?.position_id ?? "");
  }, [profile]);

  const saveProfile = useMutation({
    mutationFn: async () => {
      const body: { full_name?: string; email?: string; job_position_id?: string } = {};
      const trimmed = fullName.trim();
      if (trimmed && trimmed !== (profile?.full_name ?? "")) {
        body.full_name = trimmed;
      }
      const trimmedEmail = email.trim().toLowerCase();
      const currentEmail = (profile?.email ?? "").trim().toLowerCase();
      if (profile?.has_password && trimmedEmail && trimmedEmail !== currentEmail) {
        body.email = trimmedEmail;
      }
      const currentPos = profile?.job_positions[0]?.position_id ?? "";
      if (!isAdminUser() && jobPositionId && jobPositionId !== currentPos) {
        body.job_position_id = jobPositionId;
      }
      if (!body.full_name && !body.email && !body.job_position_id) {
        throw new Error("ไม่มีข้อมูลที่เปลี่ยนแปลง");
      }
      return api.updateMyProfile(body);
    },
    onSuccess: async (data) => {
      await persistLogin(data.token, data.username || getUsername() || "", {
        email: data.email,
        fullName: data.full_name,
        pictureUrl: data.picture_url,
      });
      void queryClient.invalidateQueries({ queryKey: queryKeys.myProfile() });
      setProfileMessage("บันทึกข้อมูลส่วนตัวแล้ว");
      setFormError("");
      setPasswordMessage("");
    },
    onError: (err) => {
      setFormError(parseApiError(err));
      setProfileMessage("");
    },
  });

  const uploadProfilePicture = useMutation({
    mutationFn: (file: File) => api.uploadProfilePicture(file),
    onSuccess: async (data) => {
      await persistLogin(data.token, data.username || getUsername() || "", {
        email: data.email,
        fullName: data.full_name,
        pictureUrl: data.picture_url,
      });
      void queryClient.invalidateQueries({ queryKey: queryKeys.myProfile() });
      setProfileMessage("อัปเดตรูปโปรไฟล์แล้ว");
      setPasswordMessage("");
      setFormError("");
    },
    onError: (err) => {
      setFormError(parseApiError(err));
      setProfileMessage("");
    },
  });

  const deleteProfilePicture = useMutation({
    mutationFn: () => api.deleteProfilePicture(),
    onSuccess: async (data) => {
      await persistLogin(data.token, data.username || getUsername() || "", {
        email: data.email,
        fullName: data.full_name,
        pictureUrl: data.picture_url,
      });
      void queryClient.invalidateQueries({ queryKey: queryKeys.myProfile() });
      setProfileMessage("ลบรูปโปรไฟล์แล้ว");
      setPasswordMessage("");
      setFormError("");
    },
    onError: (err) => {
      setFormError(parseApiError(err));
      setProfileMessage("");
    },
  });

  const changePassword = useMutation({
    mutationFn: async () => {
      if (newPassword !== confirmPassword) {
        throw new Error("รหัสผ่านใหม่ไม่ตรงกัน");
      }
      return api.changePassword({
        current_password: currentPassword,
        new_password: newPassword,
      });
    },
    onSuccess: async (data) => {
      await persistLogin(data.token, data.username || getUsername() || "", {
        email: data.email,
        fullName: data.full_name,
        pictureUrl: data.picture_url,
      });
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setPasswordMessage("เปลี่ยนรหัสผ่านแล้ว");
      setFormError("");
      setProfileMessage("");
    },
    onError: (err) => {
      setFormError(parseApiError(err));
      setPasswordMessage("");
    },
  });

  const backHref = "/chat";

  if (isLoading) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center text-gemini-muted">
        <Loader2 className="h-6 w-6 animate-spin" aria-hidden />
        <span className="sr-only">กำลังโหลด…</span>
      </div>
    );
  }

  if (error || !profile) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-10">
        <p className="text-sm text-red-400">โหลดข้อมูลไม่สำเร็จ — {parseApiError(error)}</p>
        <Link href={backHref} className="mt-4 inline-block text-sm text-gemini-blue hover:underline">
          กลับ
        </Link>
      </div>
    );
  }

  const displayName = profile.full_name || profile.username;
  const initials = userInitials(displayName);
  const showJobPosition = !profile.roles.includes("admin") && !profile.is_super_admin;
  const profilePictureBusy = uploadProfilePicture.isPending || deleteProfilePicture.isPending;

  const handleProfilePictureSelected = (file: File | undefined) => {
    if (!file) return;
    setProfileMessage("");
    setPasswordMessage("");
    setFormError("");
    if (!PROFILE_IMAGE_TYPES.has(file.type)) {
      setFormError("รองรับเฉพาะรูป JPG, PNG หรือ WebP");
      return;
    }
    if (file.size > PROFILE_IMAGE_MAX_BYTES) {
      setFormError("รูปโปรไฟล์ต้องไม่เกิน 2 MB");
      return;
    }
    uploadProfilePicture.mutate(file);
  };

  return (
    <div className="mx-auto w-full max-w-2xl px-4 py-8 sm:px-6 sm:py-10">
      <div className="mb-8 flex items-center gap-3">
        <Link
          href={getPostLoginPath() || backHref}
          className="inline-flex h-10 w-10 items-center justify-center rounded-full border border-gemini-border/70 text-gemini-muted hover:bg-gemini-hover gemini-focus-ring"
          aria-label="กลับ"
        >
          <ArrowLeft className="h-4 w-4" />
        </Link>
        <div>
          <h1 className="text-xl font-medium text-gemini-text dark:text-gemini-dark-text">
            ข้อมูลส่วนตัว
          </h1>
          <p className="text-sm text-gemini-muted dark:text-gemini-dark-muted">
            จัดการชื่อแสดง ตำแหน่งงาน และรหัสผ่านของคุณ
          </p>
        </div>
      </div>

      {formError && (
        <div
          role="alert"
          className="mb-6 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2.5 text-sm text-red-300"
        >
          {formError}
        </div>
      )}

      <ProfileHeader profile={profile} initials={initials} />

      <section className="mt-8 space-y-6">
        <Card title="รูปโปรไฟล์" icon={<Camera className="h-4 w-4" />}>
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
            <ProfileAvatar profile={profile} initials={initials} sizeClass="h-20 w-20" />
            <div className="flex-1 min-w-0 space-y-3">
              <input
                ref={fileInputRef}
                type="file"
                accept="image/jpeg,image/png,image/webp"
                className="hidden"
                onChange={(e) => {
                  handleProfilePictureSelected(e.target.files?.[0]);
                  e.currentTarget.value = "";
                }}
              />
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={profilePictureBusy}
                  className={secondaryBtn}
                >
                  <Upload className="h-4 w-4" />
                  {uploadProfilePicture.isPending ? "กำลังอัปโหลด…" : "อัปโหลดรูป"}
                </button>
                {profile.picture_url && (
                  <button
                    type="button"
                    onClick={() => deleteProfilePicture.mutate()}
                    disabled={profilePictureBusy}
                    className={dangerBtn}
                  >
                    <Trash2 className="h-4 w-4" />
                    ลบรูป
                  </button>
                )}
              </div>
              <p className="text-xs text-gemini-muted dark:text-gemini-dark-muted">
                JPG, PNG หรือ WebP ขนาดไม่เกิน 2 MB
              </p>
            </div>
          </div>
        </Card>

        <Card title="แก้ไขข้อมูล" icon={<UserRound className="h-4 w-4" />}>
          <label className="block text-sm">
            <span className="text-gemini-muted dark:text-gemini-dark-muted">ชื่อที่แสดง</span>
            <input
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              className={inputClass}
              placeholder="ชื่อ-นามสกุล"
              autoComplete="name"
            />
          </label>

          <label className="block text-sm">
            <span className="text-gemini-muted dark:text-gemini-dark-muted">อีเมล</span>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className={inputClass}
              placeholder="name@example.com"
              autoComplete="email"
              disabled={!profile.has_password}
            />
            {!profile.has_password && (
              <span className="mt-1 block text-xs text-gemini-muted dark:text-gemini-dark-muted">
                บัญชี Google จะใช้อีเมลจาก Google โดยอัตโนมัติ
              </span>
            )}
          </label>

          {showJobPosition && (
            <label className="block text-sm">
              <span className="text-gemini-muted dark:text-gemini-dark-muted">ตำแหน่งงาน</span>
              <select
                value={jobPositionId}
                onChange={(e) => setJobPositionId(e.target.value)}
                className={inputClass}
              >
                <option value="">— เลือกตำแหน่ง —</option>
                {jobPositions.map((pos) => (
                  <option key={pos.position_id} value={pos.position_id}>
                    {pos.name_th} ({pos.position_code})
                  </option>
                ))}
              </select>
            </label>
          )}

          <button
            type="button"
            onClick={() => {
              setProfileMessage("");
              setPasswordMessage("");
              setFormError("");
              saveProfile.mutate();
            }}
            disabled={saveProfile.isPending}
            className={primaryBtn}
          >
            {saveProfile.isPending ? "กำลังบันทึก…" : "บันทึกข้อมูล"}
          </button>
          {profileMessage && (
            <p role="status" className="text-sm text-gemini-blue dark:text-gemini-dark-blue">
              {profileMessage}
            </p>
          )}
        </Card>

        <Card title="โรงงานที่เข้าถึงได้" icon={<Building2 className="h-4 w-4" />}>
          <p className="text-xs text-gemini-muted dark:text-gemini-dark-muted mb-3">
            สิทธิโรงงานกำหนดโดยผู้ดูแลระบบ — เปลี่ยนโรงงานที่ใช้งานได้จากเมนูด้านข้างหลัง login
          </p>
          <ul className="space-y-2">
            {profile.factories.map((factory) => {
              const access =
                profile.factory_access.find((a) => a.factory_id === factory.factory_id)
                  ?.access_level ?? "read";
              return (
                <li
                  key={factory.factory_id}
                  className="flex items-center justify-between rounded-lg border border-gemini-border/60 px-3 py-2 text-sm"
                >
                  <span>
                    <span className="font-medium">{factory.factory_name}</span>
                    <span className="ml-2 font-mono text-xs text-gemini-muted">
                      {factory.factory_id}
                    </span>
                  </span>
                  <span className="text-xs text-gemini-muted">
                    {ACCESS_LABELS[access] ?? access}
                  </span>
                </li>
              );
            })}
          </ul>
        </Card>

        <Card title="บัญชีและความเป็นส่วนตัว" icon={<Shield className="h-4 w-4" />}>
          <dl className="grid gap-3 text-sm sm:grid-cols-2">
            <InfoRow label="ชื่อผู้ใช้" value={profile.username} />
            <InfoRow label="อีเมล" value={resolveUserEmail(profile.email) || "—"} />
            <InfoRow
              label="ระดับสิทธิ"
              value={profile.roles.map((r) => roleDisplayLabel(r)).join(", ")}
            />
            <InfoRow
              label="นโยบายความเป็นส่วนตัว"
              value={
                profile.privacy_policy_accepted_at
                  ? `ยอมรับแล้ว (${profile.privacy_policy_version ?? "—"})`
                  : "ยังไม่ยอมรับ"
              }
            />
          </dl>
          <Link href="/privacy" className="mt-3 inline-block text-sm text-gemini-blue hover:underline">
            อ่านนโยบายความเป็นส่วนตัว
          </Link>
        </Card>

        {profile.has_password && (
          <Card title="เปลี่ยนรหัสผ่าน" icon={<KeyRound className="h-4 w-4" />}>
            <label className="block text-sm">
              <span className="text-gemini-muted dark:text-gemini-dark-muted">รหัสผ่านปัจจุบัน</span>
              <input
                type="password"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                className={inputClass}
                autoComplete="current-password"
              />
            </label>
            <label className="block text-sm">
              <span className="text-gemini-muted dark:text-gemini-dark-muted">รหัสผ่านใหม่</span>
              <input
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                className={inputClass}
                autoComplete="new-password"
                minLength={8}
              />
            </label>
            <label className="block text-sm">
              <span className="text-gemini-muted dark:text-gemini-dark-muted">ยืนยันรหัสผ่านใหม่</span>
              <input
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                className={inputClass}
                autoComplete="new-password"
                minLength={8}
              />
            </label>
            <button
              type="button"
              onClick={() => {
                setProfileMessage("");
                setPasswordMessage("");
                setFormError("");
                changePassword.mutate();
              }}
              disabled={
                changePassword.isPending ||
                !currentPassword ||
                !newPassword ||
                !confirmPassword
              }
              className={primaryBtn}
            >
              {changePassword.isPending ? "กำลังเปลี่ยน…" : "เปลี่ยนรหัสผ่าน"}
            </button>
            {passwordMessage && (
              <p role="status" className="text-sm text-gemini-blue dark:text-gemini-dark-blue">
                {passwordMessage}
              </p>
            )}
          </Card>
        )}
      </section>
    </div>
  );
}

function ProfileHeader({
  profile,
  initials,
}: {
  profile: UserProfile;
  initials: string;
}) {
  return (
    <div className="flex items-center gap-4 rounded-2xl border border-gemini-border/70 bg-gemini-surface/50 dark:bg-gemini-dark-surface/50 px-5 py-5">
      <ProfileAvatar profile={profile} initials={initials} sizeClass="h-16 w-16" />
      <div className="min-w-0">
        <p className="text-lg font-medium text-gemini-text dark:text-gemini-dark-text truncate">
          {profile.full_name || profile.username}
        </p>
        {profile.email && (
          <p className="text-sm text-gemini-muted dark:text-gemini-dark-muted truncate">
            {profile.email}
          </p>
        )}
        <p className="text-xs text-gemini-muted mt-1">
          {profile.has_password ? "เข้าสู่ระบบด้วยรหัสผ่าน" : "เข้าสู่ระบบด้วย Google"}
        </p>
      </div>
    </div>
  );
}

function ProfileAvatar({
  profile,
  initials,
  sizeClass,
}: {
  profile: UserProfile;
  initials: string;
  sizeClass: string;
}) {
  if (profile.picture_url) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={profile.picture_url}
        alt={profile.full_name?.trim() || profile.username}
        referrerPolicy="no-referrer"
        className={cn(
          "shrink-0 rounded-full object-cover ring-2 ring-gemini-bg dark:ring-gemini-dark-bg",
          sizeClass
        )}
      />
    );
  }
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-[#4285f4] via-[#a855f7] to-[#ec4899] font-medium text-white",
        sizeClass,
        sizeClass.includes("20") ? "text-2xl" : "text-xl"
      )}
    >
      {initials}
    </span>
  );
}

function Card({
  title,
  icon,
  children,
}: {
  title: string;
  icon: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="rounded-2xl border border-gemini-border/70 dark:border-gemini-dark-border/70 bg-gemini-bg dark:bg-gemini-dark-bg p-5 space-y-4">
      <div className="flex items-center gap-2 border-b border-gemini-border/50 pb-3">
        <span className="text-gemini-muted">{icon}</span>
        <h2 className="text-sm font-medium text-gemini-text dark:text-gemini-dark-text">{title}</h2>
      </div>
      {children}
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-gemini-muted dark:text-gemini-dark-muted">{label}</dt>
      <dd className="mt-0.5 font-medium text-gemini-text dark:text-gemini-dark-text break-all">
        {value}
      </dd>
    </div>
  );
}

const inputClass = cn(
  "mt-1.5 w-full h-11 rounded-lg border border-gemini-border dark:border-gemini-dark-border",
  "bg-gemini-bg dark:bg-gemini-dark-bg px-3 text-sm text-gemini-text dark:text-gemini-dark-text",
  "focus:outline-none focus:ring-1 focus:ring-gemini-blue dark:focus:ring-gemini-dark-blue"
);

const primaryBtn = cn(
  "h-10 rounded-lg px-4 text-sm font-medium text-white gemini-focus-ring",
  "bg-gemini-blue dark:bg-gemini-dark-blue hover:opacity-90",
  "disabled:opacity-50 disabled:cursor-not-allowed"
);

const secondaryBtn = cn(
  "inline-flex h-10 items-center gap-2 rounded-lg border border-gemini-border dark:border-gemini-dark-border px-3 text-sm font-medium",
  "text-gemini-text dark:text-gemini-dark-text hover:bg-gemini-hover dark:hover:bg-gemini-dark-hover gemini-focus-ring",
  "disabled:opacity-50 disabled:cursor-not-allowed"
);

const dangerBtn = cn(
  "inline-flex h-10 items-center gap-2 rounded-lg border border-red-500/40 px-3 text-sm font-medium",
  "text-red-300 hover:bg-red-500/10 gemini-focus-ring",
  "disabled:opacity-50 disabled:cursor-not-allowed"
);
