"use client";

import { FactorySelectStep } from "@/components/login/FactorySelectStep";
import { JobPositionSelectStep } from "@/components/login/JobPositionSelectStep";
import { PrivacyPolicyAcceptStep } from "@/components/login/PrivacyPolicyAcceptStep";
import { useJobPositions } from "@/hooks/useJobPositions";
import { GeminiAuthInput } from "@/components/auth/GeminiAuthInput";
import { GoogleSignInButton } from "@/components/auth/GoogleSignInButton";
import { AuthLayout, AuthPanel } from "@/components/auth/AuthLayout";
import { AuthDivider, AuthTab } from "@/components/auth/AuthDivider";
import { api, type LoginResponse } from "@/lib/api";
import {
  PRIVACY_ONBOARD_PARAM,
  PRIVACY_ONBOARD_VALUE,
  SWITCH_ACCOUNT_PARAM,
  consumeApiUnreachableFlag,
  consumeSessionExpiredFlag,
  getPostLoginPath,
  logoutSession,
  needsPrivacyAcceptance,
  persistLogin,
  refreshAuthProfile,
  stageOnboardingSession,
} from "@/lib/auth";
import {
  isAdminLogin,
  resolveDefaultFactoryId,
  shouldShowFactoryStep,
} from "@/lib/loginFlow";
import { parseApiError } from "@/lib/errors";
import { cn } from "@/lib/cn";
import { useUiStore } from "@/stores/uiStore";
import { useQueryClient } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import { LoadingState } from "@/components/ui/State";
import {
  consumeOAuthLogin,
  oauthErrorMessage,
  startGoogleSignIn,
} from "@/lib/googleAuth";

type Step = "credentials" | "factory" | "privacy" | "job_position";

const passwordLoginEnabled = process.env.NEXT_PUBLIC_PASSWORD_LOGIN !== "false";

export type AuthFormProps = {
  /** Kept for API compatibility; self-service signup is not offered. */
  initialMode?: "signin";
};

export function AuthForm({ initialMode: _initialMode = "signin" }: AuthFormProps) {
  return (
    <Suspense
      fallback={
        <AuthLayout>
          <LoadingState message="กำลังโหลด…" />
        </AuthLayout>
      }
    >
      <AuthFormInner />
    </Suspense>
  );
}

function AuthFormInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const setSelectedFactoryId = useUiStore((s) => s.setSelectedFactoryId);
  const setSelectedFactoryIds = useUiStore((s) => s.setSelectedFactoryIds);

  const [step, setStep] = useState<Step>("credentials");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [sessionNotice, setSessionNotice] = useState("");
  const [loading, setLoading] = useState(false);
  const [googleLoading, setGoogleLoading] = useState(false);

  const [loginResult, setLoginResult] = useState<LoginResponse | null>(null);
  const [selectedFactories, setSelectedFactories] = useState<string[]>([]);
  const [selectedJobPosition, setSelectedJobPosition] = useState("");
  const jobPositionsEnabled = step === "job_position" || step === "privacy" || step === "factory";
  const { data: jobPositions = [], isLoading: jobPositionsLoading } = useJobPositions(jobPositionsEnabled);

  useEffect(() => {
    if (consumeSessionExpiredFlag()) {
      setSessionNotice("เซสชันหมดอายุ — กรุณาเข้าสู่ระบบใหม่");
    }
    if (consumeApiUnreachableFlag()) {
      setSessionNotice(
        "Cannot reach the API — ensure the backend is running on port 8000, then try again."
      );
    }
  }, []);

  useEffect(() => {
    if (searchParams.get(SWITCH_ACCOUNT_PARAM) === "1") {
      setSessionNotice("ออกจากระบบแล้ว — เข้าสู่ระบบด้วยบัญชีอื่น");
    }
  }, [searchParams]);

  useEffect(() => {
    if (searchParams.get(PRIVACY_ONBOARD_PARAM) !== PRIVACY_ONBOARD_VALUE) return;
    void refreshAuthProfile().then((profile) => {
      if (!profile || !needsPrivacyAcceptance()) return;
      setStep("privacy");
      setInfo("อ่านนโยบายความเป็นส่วนตัวและยอมรับก่อนเข้าใช้งาน");
      setSessionNotice("ต้องยอมรับนโยบายความเป็นส่วนตัวจึงจะใช้งาน Neo ได้");
    });
  }, [searchParams]);

  useEffect(() => {
    const errorCode = searchParams.get("error");
    if (errorCode) {
      setError(oauthErrorMessage(errorCode, searchParams.get("message")));
    }
  }, [searchParams]);

  const beginPrivacyStep = useCallback(async (data: LoginResponse) => {
    await stageOnboardingSession(data.token, data.username || username);
    setStep("privacy");
    setInfo("อ่านนโยบายความเป็นส่วนตัวและยอมรับก่อนเข้าใช้งาน");
  }, [username]);

  const beginJobPositionStep = useCallback(async (data: LoginResponse) => {
    await stageOnboardingSession(data.token, data.username || username);
    setStep("job_position");
    setInfo("เลือกตำแหน่งงานของคุณเพื่อเริ่มใช้งาน");
  }, [username]);

  const completeLogin = useCallback(
    async (data: LoginResponse, factoryIds: string[]) => {
      queryClient.clear();
      useUiStore.getState().resetSession();
      const synced = await persistLogin(data.token, data.username || username, {
        email: data.email,
        fullName: data.full_name,
        pictureUrl: data.picture_url,
      });
      if (!synced) {
        throw new Error(
          "Could not start session — check that the API is running on port 8000."
        );
      }
      setSelectedFactoryIds(factoryIds);
      setSelectedFactoryId(factoryIds[0] ?? null);
      const dest = getPostLoginPath(searchParams.get("from"));
      router.replace(dest);
      window.setTimeout(() => {
        if (window.location.pathname === "/login" || window.location.pathname === "/signup") {
          window.location.assign(dest);
        }
      }, 400);
    },
    [queryClient, username, setSelectedFactoryId, setSelectedFactoryIds, router, searchParams]
  );

  const continueAfterOnboarding = useCallback(
    async (data: LoginResponse, factoryIds: string[]) => {
      if (data.needs_job_position) {
        await beginJobPositionStep(data);
        return;
      }
      await completeLogin(data, factoryIds);
    },
    [beginJobPositionStep, completeLogin]
  );

  const beginFactoryStep = useCallback((data: LoginResponse) => {
    setSelectedFactories(data.factories.map((f) => f.factory_id));
    setStep("factory");
    setInfo("เข้าสู่ระบบแล้ว — เลือกโรงงานที่ต้องการใช้งาน");
  }, []);

  const continueAfterFactoryResolution = useCallback(
    async (data: LoginResponse) => {
      if (shouldShowFactoryStep(data)) {
        beginFactoryStep(data);
        return;
      }
      const factoryId = resolveDefaultFactoryId(data);
      const factoryIds = isAdminLogin(data)
        ? data.factories.map((f) => f.factory_id)
        : factoryId
          ? [factoryId]
          : [];
      if (factoryIds.length > 0) setSelectedFactories(factoryIds);
      await continueAfterOnboarding(data, factoryIds);
    },
    [beginFactoryStep, continueAfterOnboarding]
  );

  const beginPostCredentialsFlow = useCallback(
    async (data: LoginResponse) => {
      setLoginResult(data);
      if (data.needs_privacy_acceptance) {
        await beginPrivacyStep(data);
        return;
      }
      await continueAfterFactoryResolution(data);
    },
    [beginPrivacyStep, continueAfterFactoryResolution]
  );

  useEffect(() => {
    if (searchParams.get("oauth") !== "1") return;

    const payload = consumeOAuthLogin();
    if (!payload) return;

    const loginData: LoginResponse = {
      token: payload.token,
      token_type: "bearer",
      expires_in: 8 * 3600,
      username: payload.username,
      email: payload.email,
      full_name: payload.fullName,
      picture_url: payload.pictureUrl,
	      factories: payload.factories,
	      needs_job_position: payload.needs_job_position,
	      needs_privacy_acceptance: payload.needs_privacy_acceptance,
	      is_super_admin: payload.is_super_admin,
	    };
    setLoginResult(loginData);

    void beginPostCredentialsFlow(loginData);
  }, [searchParams, beginPostCredentialsFlow]);

  async function onSubmitCredentials(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError("");
    setInfo("");
    setSessionNotice("");

    const form = e.currentTarget;
    const formUsername =
      (form.elements.namedItem("username") as HTMLInputElement | null)?.value ??
      username;
    const formPassword =
      (form.elements.namedItem("password") as HTMLInputElement | null)?.value ??
      password;

    if (formUsername !== username) setUsername(formUsername);
    if (formPassword !== password) setPassword(formPassword);

    if (!formUsername.trim() || !formPassword) {
      setError("กรุณากรอกชื่อผู้ใช้และรหัสผ่าน");
      return;
    }

    setLoading(true);
    try {
      // A successful login replaces the httpOnly cookie. Avoid an extra
      // sequential DELETE request here; it made every password login wait for
      // a round trip before authentication could even start.
      queryClient.clear();
      useUiStore.getState().resetSession();
      const data = await api.login(formUsername.trim(), formPassword);
      await beginPostCredentialsFlow(data);
    } catch (err) {
      setError(parseApiError(err));
    } finally {
      setLoading(false);
    }
  }

  async function onContinueFactory() {
    if (!loginResult || selectedFactories.length === 0) return;
    setLoading(true);
    setError("");
    try {
      await continueAfterOnboarding(loginResult, selectedFactories);
    } catch (err) {
      setError(parseApiError(err));
    } finally {
      setLoading(false);
    }
  }

  async function onAcceptPrivacy() {
    setLoading(true);
    setError("");
    try {
      const updated = await api.acceptPrivacyPolicy();
      setLoginResult(updated);
      await stageOnboardingSession(updated.token, updated.username || username);
      if (shouldShowFactoryStep(updated)) {
        beginFactoryStep(updated);
        return;
      }
      const factoryId = resolveDefaultFactoryId(updated);
      const factoryIds = factoryId ? [factoryId] : [];
      if (factoryIds.length > 0) setSelectedFactories(factoryIds);
      await continueAfterOnboarding(updated, factoryIds);
    } catch (err) {
      setError(parseApiError(err));
    } finally {
      setLoading(false);
    }
  }

  async function onDeclinePrivacy() {
    setLoading(true);
    try {
      await logoutSession(queryClient);
      setLoginResult(null);
      setStep("credentials");
      setError("");
      setInfo("");
      setSessionNotice("ต้องยอมรับนโยบายความเป็นส่วนตัวจึงจะใช้งาน Neo ได้");
      router.replace("/login");
    } finally {
      setLoading(false);
    }
  }

  async function onContinueJobPosition() {
    if (!loginResult || !selectedJobPosition) return;
    setLoading(true);
    setError("");
    try {
      const updated = await api.setMyJobPosition(selectedJobPosition);
      setLoginResult(updated);
      const factoryIds =
        selectedFactories.length > 0
          ? selectedFactories
          : resolveDefaultFactoryId(updated)
            ? [resolveDefaultFactoryId(updated)!]
            : [];
      await completeLogin(updated, factoryIds);
    } catch (err) {
      setError(parseApiError(err));
    } finally {
      setLoading(false);
    }
  }

  async function onGoogleSignIn() {
    setError("");
    setInfo("");
    setGoogleLoading(true);
    try {
      await startGoogleSignIn(searchParams.get("from"));
    } catch {
      setGoogleLoading(false);
      setError("เริ่ม Google sign-in ไม่ได้ — กรุณาลองอีกครั้ง");
    }
  }

  const stepTitle =
    step === "factory"
      ? "เลือกโรงงาน"
      : step === "privacy"
        ? "นโยบายความเป็นส่วนตัว"
        : step === "job_position"
          ? "เลือกตำแหน่งงาน"
          : "เข้าสู่ระบบ";

  const stepNumber =
    step === "credentials" ? 1 : step === "privacy" ? 2 : step === "factory" ? 3 : 4;
  const totalSteps = 4;

  const canSubmitCredentials =
    Boolean(username.trim()) && Boolean(password) && !loading;

  const FormShell = AuthPanel;

  return (
    <AuthLayout>
      <FormShell>
        {step === "credentials" ? (
          <div className="mb-8 flex justify-center gap-4">
            <AuthTab active={false} href="/signup">
              Sign Up
            </AuthTab>
            <AuthTab active>Log In</AuthTab>
          </div>
        ) : (
          <>
            <p className="text-xs text-[var(--auth-muted)] mb-2">ขั้นที่ {stepNumber}/{totalSteps}</p>
            <h1 className="text-lg font-medium text-[var(--auth-text)] mb-6">{stepTitle}</h1>
          </>
        )}

        {sessionNotice && (
          <div
            role="alert"
            className="mb-6 px-3 py-2 rounded-md text-sm text-[var(--auth-muted)] border auth-subtle-box"
          >
            {sessionNotice}
          </div>
        )}

        {error && (
          <div
            role="alert"
            className="mb-5 px-3 py-2.5 rounded-lg text-sm border auth-alert-error"
          >
            {error}
          </div>
        )}

        {info && (
          <div
            role="status"
            className="mb-5 px-3 py-2.5 rounded-lg text-sm border auth-alert-info"
          >
            {info}
          </div>
        )}

        <div
          className={cn(
            "transition-all duration-300 ease-in-out",
            step === "credentials" ? "opacity-100 translate-y-0" : "hidden"
          )}
        >
          {step === "credentials" && (
            <>
              <AuthDivider label="Log in with" />
              <div className="auth-oauth-row">
                <GoogleSignInButton
                  onClick={onGoogleSignIn}
                  disabled={loading}
                  loading={googleLoading}
                  variant="compact"
                />
              </div>

              {passwordLoginEnabled && (
                <>
                  <AuthDivider label="or continue with email" />

                  <form
                    id="auth-credentials-form"
                    onSubmit={onSubmitCredentials}
                    className="flex flex-col gap-4"
                  >
                    <GeminiAuthInput
                      label="Email"
                      name="username"
                      variant="auth"
                      value={username}
                      onChange={(e) => setUsername(e.target.value)}
                      autoComplete="username"
                      disabled={loading}
                      placeholder="Your email address"
                    />

                    <GeminiAuthInput
                      label="Password"
                      name="password"
                      type="password"
                      variant="auth"
                      showPasswordToggle
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      autoComplete="current-password"
                      disabled={loading}
                      placeholder="Your password"
                    />

                    <button
                      type="submit"
                      disabled={loading || !canSubmitCredentials}
                      className={cn(
                        "auth-continue-btn gemini-focus-ring",
                        loading && "opacity-80 cursor-wait"
                      )}
                    >
                      {loading ? "Please wait…" : "Continue"}
                    </button>
                  </form>

                  <button
                    type="button"
                    className="auth-forgot-btn"
                    title="Contact your plant administrator to reset access"
                  >
                    Forgot Password?
                  </button>

                  <p className="auth-terms">
                    By continuing, you agree to our{" "}
                    <a href="/privacy">Terms of Service</a> and{" "}
                    <a href="/privacy">Privacy Policy</a>.
                  </p>
                </>
              )}
            </>
          )}
        </div>

        {step === "factory" && loginResult && (
          <div className="opacity-100 transition-opacity duration-300">
            <FactorySelectStep
              factories={loginResult.factories}
              value={selectedFactories}
              onChange={setSelectedFactories}
              onContinue={onContinueFactory}
              loading={loading}
            />
            <button
              type="button"
              onClick={() => {
                setStep("credentials");
                setLoginResult(null);
                setError("");
              }}
              className="mt-5 w-full text-center text-sm text-[var(--auth-muted)] hover:text-[var(--auth-text)] transition-colors"
            >
              ← กลับไปหน้าเข้าสู่ระบบ
            </button>
          </div>
        )}

        {step === "privacy" && (
          <div className="opacity-100 transition-opacity duration-300">
            <PrivacyPolicyAcceptStep
              onAccept={() => void onAcceptPrivacy()}
              onDecline={() => void onDeclinePrivacy()}
              loading={loading}
            />
          </div>
        )}

        {step === "job_position" && loginResult && (
          <div className="opacity-100 transition-opacity duration-300">
            <JobPositionSelectStep
              positions={jobPositions}
              value={selectedJobPosition}
              onChange={setSelectedJobPosition}
              onContinue={onContinueJobPosition}
              loading={loading || jobPositionsLoading}
            />
            <button
              type="button"
              onClick={() => {
                void logoutSession(queryClient);
                setStep("credentials");
                setLoginResult(null);
                setSelectedJobPosition("");
                setError("");
              }}
              className="mt-5 w-full text-center text-sm text-[var(--auth-muted)] hover:text-[var(--auth-text)] transition-colors"
            >
              ← กลับไปหน้าเข้าสู่ระบบ
            </button>
          </div>
        )}
      </FormShell>
    </AuthLayout>
  );
}
