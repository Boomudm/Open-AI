from __future__ import annotations

import io
import re
import uuid
from urllib.parse import urlencode, urlparse

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import RedirectResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from spark.api.openapi_responses import WRITE_ERRORS
from spark.core.auth import hash_password, issue_token, verify_password, verify_token
from spark.core.config import settings
from spark.core.database import get_session
from spark.core.google_oauth import (
    GoogleOAuthError,
    OAuthStateError,
    build_google_authorize_url,
    email_allowed_for_oauth,
    fetch_google_userinfo,
    google_oauth_configured,
    sign_oauth_state,
    validate_oauth_web_origin,
    verify_oauth_state,
)
from spark.core.logging import get_logger
from spark.core.oauth_exchange import consume_oauth_exchange_payload, store_oauth_exchange_payload
from spark.core.privacy_policy import PRIVACY_POLICY_VERSION
from spark.core.security import Principal, get_principal, principal_from_token
from spark.db.models.job_positions import JobPosition, UserJobPosition
from spark.db.models.org import Factory, Role, User, UserFactoryAccess, UserRole
from spark.schemas.factories import FactoryBrief as FactoryBriefSchema
from spark.schemas.job_positions import FactoryAccessEntry, JobPositionBrief
from spark.schemas.user_profile import ChangePasswordRequest, UserProfileOut, UserProfileUpdate
from spark.services.image_mime import (
    guess_image_mime_from_name,
    is_allowed_image_mime,
)
from spark.services.auth_session import bump_user_token_version, token_version_matches
from spark.services.job_position_service import set_user_job_positions
from spark.storage import get_storage
from spark.storage.keys import key_to_local_path, profile_image_object_key
from spark.storage.resolve import open_storage_object_async
from spark.storage.uri import build_file_uri, build_s3_uri

router = APIRouter(prefix="/auth", tags=["Auth"])

log = get_logger(__name__)
_USERNAME_MAX_LEN = 50
_PROFILE_IMAGE_MIMES = ("image/jpeg", "image/png", "image/webp")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class GoogleAccountConflictError(Exception):
    """Raised when Google sub cannot be linked to an existing Neo Chat user."""


def _username_base_from_email(email: str) -> str:
    local = email.split("@", 1)[0]
    base = re.sub(r"[^a-zA-Z0-9_]", "_", local).strip("_").lower()
    return (base or "user")[: _USERNAME_MAX_LEN - 4]


async def _resolve_unique_username(session: AsyncSession, email: str) -> str:
    base = _username_base_from_email(email)
    for n in range(1, 1000):
        if n == 1:
            candidate = base
        else:
            suffix = f"_{n}"
            candidate = f"{base[: _USERNAME_MAX_LEN - len(suffix)]}{suffix}"
        existing = await session.scalar(select(User).where(User.username == candidate))
        if not existing:
            return candidate
    raise RuntimeError("could not allocate unique username")


async def _assign_default_google_access(session: AsyncSession, user: User) -> None:
    role_code = settings.google_oauth_default_role.strip() or "employee"
    role = await session.scalar(select(Role).where(Role.role_code == role_code))
    if role:
        session.add(UserRole(user_id=user.user_id, role_id=role.role_id))

    factory_id = settings.google_oauth_default_factory_id.strip()
    factory = None
    if factory_id:
        factory = await session.scalar(select(Factory).where(Factory.factory_id == factory_id))
    if factory is None:
        factory = await session.scalar(select(Factory).order_by(Factory.factory_id).limit(1))
    if factory:
        session.add(
            UserFactoryAccess(
                user_id=user.user_id,
                factory_id=factory.factory_id,
                access_level="read",
            )
        )


async def _provision_google_user(
    session: AsyncSession,
    *,
    email: str,
    full_name: str | None,
    google_id: str,
    picture_url: str | None,
) -> User:
    username = await _resolve_unique_username(session, email)
    user = User(
        username=username,
        full_name=full_name,
        email=email,
        google_id=google_id,
        picture_url=picture_url,
        password_hash=None,
        is_active=True,
    )
    session.add(user)
    await session.flush()
    await _assign_default_google_access(session, user)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        existing = await session.scalar(select(User).where(User.google_id == google_id))
        if existing:
            return existing
        existing = await session.scalar(
            select(User).where(func.lower(User.email) == email.lower())
        )
        if existing:
            return existing
        raise
    await session.refresh(user)
    return user


def _looks_like_google_sub(username: str, google_id: str) -> bool:
    return username.strip() == google_id.strip()


async def _repair_legacy_google_username(
    session: AsyncSession, user: User, *, email: str, google_id: str
) -> None:
    """Fix accounts created before google_id existed (username was set to Google sub)."""
    if not _looks_like_google_sub(user.username, google_id):
        return
    user.username = await _resolve_unique_username(session, email)


def _is_local_profile_picture_url(url: str | None) -> bool:
    return bool(url and url.startswith("/api/v1/auth/profile-picture/"))


def _apply_google_profile_to_user(
    user: User,
    *,
    email: str,
    google_id: str,
    full_name: str | None,
    picture_url: str | None,
) -> None:
    user.google_id = google_id
    user.email = email
    if full_name and (not user.full_name or user.password_hash is None):
        user.full_name = full_name
    if picture_url and not _is_local_profile_picture_url(user.picture_url):
        user.picture_url = picture_url


async def _upsert_google_user(session: AsyncSession, profile: dict) -> User | None:
    google_id = (profile.get("sub") or "").strip()
    email = (profile.get("email") or "").strip()
    full_name = profile.get("name")
    picture_url = profile.get("picture")

    if not google_id:
        return None
    if not email:
        return None
    if profile.get("email_verified") is False:
        return None

    user = await session.scalar(select(User).where(User.google_id == google_id))

    if user is None:
        user = await session.scalar(
            select(User).where(func.lower(User.email) == email.lower())
        )
        if user is not None:
            if user.google_id and user.google_id != google_id:
                raise GoogleAccountConflictError("email linked to another Google account")
            _apply_google_profile_to_user(
                user,
                email=email,
                google_id=google_id,
                full_name=full_name,
                picture_url=picture_url,
            )

    if user is None:
        user = await session.scalar(select(User).where(User.username == google_id))
        if user is not None and user.google_id is None:
            _apply_google_profile_to_user(
                user,
                email=email,
                google_id=google_id,
                full_name=full_name,
                picture_url=picture_url,
            )
            await _repair_legacy_google_username(session, user, email=email, google_id=google_id)

    if user is None:
        user = await _provision_google_user(
            session,
            email=email,
            full_name=full_name,
            google_id=google_id,
            picture_url=picture_url,
        )
        log.info("oauth_user_created", user_id=str(user.user_id), email_domain=email.split("@")[-1])
        return user

    if not user.is_active:
        return None

    should_log_link = user.google_id is None
    _apply_google_profile_to_user(
        user,
        email=email,
        google_id=google_id,
        full_name=full_name,
        picture_url=picture_url,
    )
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        return await session.scalar(select(User).where(User.google_id == google_id))
    await session.refresh(user)
    if should_log_link:
        log.info("oauth_user_linked", user_id=str(user.user_id), email_domain=email.split("@")[-1])
    else:
        log.info("oauth_login", user_id=str(user.user_id), email_domain=email.split("@")[-1])
    return user


class LoginRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{"username": "admin", "password": "changeme"}]})

    username: str = Field(examples=["admin"])
    password: str = Field(examples=["changeme"])


class FactoryBrief(BaseModel):
    factory_id: str
    factory_name: str


class TokenResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"token": "eyJ...", "token_type": "bearer", "expires_in": 28800}]}
    )

    token: str
    token_type: str = "bearer"
    expires_in: int = 8 * 3600
    username: str = ""
    email: str = ""
    full_name: str = ""
    picture_url: str = ""
    factories: list[FactoryBrief] = []
    job_position_ids: list[str] = []
    needs_job_position: bool = False
    needs_privacy_acceptance: bool = False
    is_super_admin: bool = False


class SetMyJobPositionRequest(BaseModel):
    position_id: uuid.UUID


class GoogleAuthStatus(BaseModel):
    enabled: bool


class OAuthExchangeRequest(BaseModel):
    code: str = Field(min_length=8)


def _needs_privacy_acceptance(user: User) -> bool:
    return (
        user.privacy_policy_accepted_at is None
        or user.privacy_policy_version != PRIVACY_POLICY_VERSION
    )


async def _token_response_for_user(session: AsyncSession, user: User) -> TokenResponse:
    role_rows = (
        await session.execute(
            select(Role.role_code)
            .join(UserRole, UserRole.role_id == Role.role_id)
            .where(UserRole.user_id == user.user_id)
        )
    ).scalars().all()

    access_rows = (
        await session.execute(
            select(UserFactoryAccess.factory_id, UserFactoryAccess.access_level).where(
                UserFactoryAccess.user_id == user.user_id
            )
        )
    ).all()
    access_map = {fid: lvl for fid, lvl in access_rows}
    roles = list(role_rows)
    is_admin = "admin" in roles or bool(user.is_super_admin)

    position_rows = (
        await session.execute(
            select(UserJobPosition.position_id).where(UserJobPosition.user_id == user.user_id)
        )
    ).scalars().all()
    job_position_ids = [str(pid) for pid in position_rows]

    if is_admin:
        factory_rows = (
            await session.execute(select(Factory).order_by(Factory.factory_id))
        ).scalars().all()
    elif access_map:
        factory_rows = (
            await session.execute(
                select(Factory)
                .where(Factory.factory_id.in_(access_map.keys()))
                .order_by(Factory.factory_id)
            )
        ).scalars().all()
    else:
        factory_rows = []

    privacy_version = user.privacy_policy_version or ""
    token = issue_token(
        {
            "sub": str(user.user_id),
            "username": user.username,
            "email": user.email or "",
            "name": user.full_name or "",
            "picture": user.picture_url or "",
            "roles": roles,
            "factory_access": access_map,
            "job_position_ids": job_position_ids,
            "token_version": user.token_version,
            "privacy_policy_version": privacy_version,
            "is_super_admin": bool(user.is_super_admin),
        }
    )
    return TokenResponse(
        token=token,
        username=user.username,
        email=user.email or "",
        full_name=user.full_name or "",
        picture_url=user.picture_url or "",
        factories=[
            FactoryBrief(factory_id=f.factory_id, factory_name=f.factory_name)
            for f in factory_rows
        ],
        job_position_ids=job_position_ids,
        needs_job_position=not is_admin and len(job_position_ids) == 0,
        needs_privacy_acceptance=_needs_privacy_acceptance(user),
        is_super_admin=bool(user.is_super_admin),
    )


def _origin_from_absolute_url(value: str | None) -> str | None:
    if not value or not value.strip():
        return None
    parsed = urlparse(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return validate_oauth_web_origin(f"{parsed.scheme}://{parsed.netloc}")


def _request_public_origin(request: Request) -> str | None:
    forwarded_host = request.headers.get("x-forwarded-host")
    host = (forwarded_host or request.headers.get("host") or "").split(",", 1)[0].strip()
    if not host:
        return None
    forwarded_proto = request.headers.get("x-forwarded-proto")
    proto = (forwarded_proto or request.url.scheme or "https").split(",", 1)[0].strip()
    if proto not in {"http", "https"}:
        proto = "https"
    return validate_oauth_web_origin(f"{proto}://{host}")


def _configured_web_origin() -> str | None:
    return _origin_from_absolute_url(settings.web_app_url)


def _oauth_web_origin(request: Request, state_payload: dict | None = None) -> str:
    configured = _configured_web_origin()
    if configured:
        return configured
    if state_payload:
        from_state = validate_oauth_web_origin(str(state_payload.get("web_origin") or ""))
        if from_state:
            return from_state
    from_request = _request_public_origin(request)
    if from_request:
        return from_request
    return "http://127.0.0.1:3000"


def _oauth_redirect_uri(request: Request, web_origin: str | None = None) -> str:
    configured = settings.google_oauth_callback_url.strip()
    if configured:
        return configured
    origin = validate_oauth_web_origin(web_origin) or _oauth_web_origin(request)
    return f"{origin}/api/v1/auth/google/callback"


def _web_callback_url(params: dict[str, str], *, web_origin: str | None = None) -> str:
    base = (validate_oauth_web_origin(web_origin) or _configured_web_origin() or settings.web_app_url).rstrip("/")
    return f"{base}/auth/callback?{urlencode(params)}"


def _redirect_oauth_error(code: str, message: str, *, web_origin: str | None = None) -> RedirectResponse:
    return RedirectResponse(
        _web_callback_url({"error": code, "message": message}, web_origin=web_origin),
        status_code=302,
    )


@router.get("/google/status", response_model=GoogleAuthStatus)
async def google_auth_status() -> GoogleAuthStatus:
    return GoogleAuthStatus(enabled=google_oauth_configured())


@router.get("/google/login")
async def google_login(
    request: Request,
    from_path: str | None = Query(default=None, alias="from"),
) -> RedirectResponse:
    if not google_oauth_configured():
        raise HTTPException(503, "Google sign-in is not configured")

    web_origin = _oauth_web_origin(request)
    state = sign_oauth_state(from_path, web_origin=web_origin)
    url = build_google_authorize_url(
        state=state,
        redirect_uri=_oauth_redirect_uri(request, web_origin),
    )
    return RedirectResponse(url, status_code=302)


@router.get("/google/callback")
async def google_callback(
    request: Request,
    session: AsyncSession = Depends(get_session),
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
) -> RedirectResponse:
    state_payload: dict = {}
    web_origin = _oauth_web_origin(request)
    if error:
        return _redirect_oauth_error("google_denied", error, web_origin=web_origin)

    if not google_oauth_configured():
        return _redirect_oauth_error(
            "not_configured",
            "Google sign-in is not configured",
            web_origin=web_origin,
        )

    if not code or not state:
        return _redirect_oauth_error(
            "oauth_failed",
            "Missing authorization code",
            web_origin=web_origin,
        )

    try:
        state_payload = verify_oauth_state(state)
        web_origin = _oauth_web_origin(request, state_payload)
    except OAuthStateError:
        return _redirect_oauth_error(
            "invalid_state",
            "Sign-in session expired. Please try again.",
            web_origin=web_origin,
        )

    redirect_uri = _oauth_redirect_uri(request, web_origin)
    try:
        profile = await fetch_google_userinfo(code, redirect_uri)
    except GoogleOAuthError:
        return _redirect_oauth_error(
            "google_token_failed",
            "Could not verify Google account.",
            web_origin=web_origin,
        )

    email = (profile.get("email") or "").strip()
    if not email:
        return _redirect_oauth_error(
            "no_email",
            "Google account has no email address.",
            web_origin=web_origin,
        )

    google_id = (profile.get("sub") or "").strip()
    if not google_id:
        return _redirect_oauth_error(
            "oauth_failed",
            "Google account identifier missing.",
            web_origin=web_origin,
        )

    if profile.get("email_verified") is False:
        return _redirect_oauth_error(
            "email_not_verified",
            "Your Google email address is not verified.",
            web_origin=web_origin,
        )

    if not email_allowed_for_oauth(email):
        return _redirect_oauth_error(
            "domain_not_allowed",
            "Your email domain is not authorized for this plant application.",
            web_origin=web_origin,
        )

    existing_by_email = await session.scalar(
        select(User).where(func.lower(User.email) == email.lower())
    )
    if existing_by_email and not existing_by_email.is_active:
        return _redirect_oauth_error(
            "account_inactive",
            "This account has been deactivated. Contact your administrator.",
            web_origin=web_origin,
        )

    existing_by_google = await session.scalar(select(User).where(User.google_id == google_id))
    if (
        existing_by_email
        and existing_by_google
        and existing_by_email.user_id != existing_by_google.user_id
    ):
        return _redirect_oauth_error(
            "account_conflict",
            "This Google account cannot be linked. Contact your administrator.",
            web_origin=web_origin,
        )

    if (
        existing_by_email
        and existing_by_email.google_id
        and existing_by_email.google_id != google_id
    ):
        return _redirect_oauth_error(
            "account_conflict",
            "This email is linked to a different Google account.",
            web_origin=web_origin,
        )

    try:
        user = await _upsert_google_user(session, profile)
    except GoogleAccountConflictError:
        return _redirect_oauth_error(
            "account_conflict",
            "This Google account cannot be linked. Contact your administrator.",
            web_origin=web_origin,
        )
    except IntegrityError:
        return _redirect_oauth_error(
            "signup_failed",
            "Could not create your account. Please try again.",
            web_origin=web_origin,
        )

    if not user:
        return _redirect_oauth_error(
            "oauth_failed",
            "Could not sign you in with Google.",
            web_origin=web_origin,
        )

    token_response = await _token_response_for_user(session, user)
    exchange_code = await store_oauth_exchange_payload(token_response.model_dump())
    callback_params: dict[str, str] = {"code": exchange_code}
    from_path = state_payload.get("from")
    if isinstance(from_path, str) and from_path.strip():
        callback_params["from"] = from_path.strip()
    return RedirectResponse(
        _web_callback_url(callback_params, web_origin=web_origin),
        status_code=302,
    )


@router.post("/oauth/exchange", response_model=TokenResponse)
async def oauth_exchange(payload: OAuthExchangeRequest) -> TokenResponse:
    data = await consume_oauth_exchange_payload(payload.code)
    if not data:
        raise HTTPException(401, "invalid or expired oauth code")
    return TokenResponse(**data)


@router.post("/login", response_model=TokenResponse, responses={401: {"description": "Invalid credentials"}, **WRITE_ERRORS})
async def login(
    payload: LoginRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    from spark.services.auth_login_guard import (
        assert_login_allowed,
        clear_login_failures,
        record_login_failure,
    )

    await assert_login_allowed(request, username=payload.username)
    user = await session.scalar(select(User).where(User.username == payload.username))
    if not user or not user.is_active or not user.password_hash:
        await record_login_failure(request, username=payload.username)
        raise HTTPException(401, "invalid credentials")
    if not verify_password(payload.password, user.password_hash):
        await record_login_failure(request, username=payload.username)
        raise HTTPException(401, "invalid credentials")

    await clear_login_failures(request, username=payload.username)
    return await _token_response_for_user(session, user)


@router.post("/privacy-acceptance", response_model=TokenResponse, responses=WRITE_ERRORS)
async def accept_privacy_policy(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    """First-login (or policy version bump): record privacy consent."""
    p = get_principal(request)
    if p.username == "system":
        raise HTTPException(401, "missing bearer token")
    if p.privacy_policy_version == PRIVACY_POLICY_VERSION:
        raise HTTPException(409, "privacy policy already accepted for current version")

    try:
        user_id = uuid.UUID(p.user_id)
    except ValueError as exc:
        raise HTTPException(401, "invalid token subject") from exc

    user = await session.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(401, "user not found or inactive")

    user.privacy_policy_accepted_at = datetime.now(timezone.utc)
    user.privacy_policy_version = PRIVACY_POLICY_VERSION
    await bump_user_token_version(session, user)
    await session.commit()
    await session.refresh(user)
    return await _token_response_for_user(session, user)


@router.post("/job-position", response_model=TokenResponse, responses=WRITE_ERRORS)
async def set_my_job_position(
    payload: SetMyJobPositionRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    """First-login onboarding: assign exactly one active job position to self."""
    p = get_principal(request)
    if "admin" in p.roles:
        raise HTTPException(400, "admin accounts do not require a job position")
    if p.job_position_ids:
        raise HTTPException(409, "job position is already set; contact an administrator to change it")

    try:
        user_id = uuid.UUID(p.user_id)
    except ValueError as exc:
        raise HTTPException(401, "invalid token subject") from exc

    user = await session.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(401, "user not found or inactive")

    await set_user_job_positions(session, user, [payload.position_id])
    await bump_user_token_version(session, user)
    await session.commit()
    await session.refresh(user)
    return await _token_response_for_user(session, user)


async def _user_profile_response(session: AsyncSession, user: User) -> UserProfileOut:
    role_rows = (
        await session.execute(
            select(Role.role_code)
            .join(UserRole, UserRole.role_id == Role.role_id)
            .where(UserRole.user_id == user.user_id)
        )
    ).scalars().all()
    access_rows = (
        await session.execute(
            select(UserFactoryAccess.factory_id, UserFactoryAccess.access_level).where(
                UserFactoryAccess.user_id == user.user_id
            )
        )
    ).all()
    access_map = {fid: lvl for fid, lvl in access_rows}
    roles = list(role_rows)
    is_admin = "admin" in roles or bool(user.is_super_admin)

    if is_admin:
        factory_rows = (
            await session.execute(select(Factory).order_by(Factory.factory_id))
        ).scalars().all()
    elif access_map:
        factory_rows = (
            await session.execute(
                select(Factory)
                .where(Factory.factory_id.in_(access_map.keys()))
                .order_by(Factory.factory_id)
            )
        ).scalars().all()
    else:
        factory_rows = []

    position_ids = (
        await session.execute(
            select(UserJobPosition.position_id).where(UserJobPosition.user_id == user.user_id)
        )
    ).scalars().all()
    job_positions: list[JobPositionBrief] = []
    if position_ids:
        rows = (
            await session.execute(
                select(JobPosition).where(JobPosition.position_id.in_(position_ids))
            )
        ).scalars().all()
        job_positions = [JobPositionBrief.model_validate(row) for row in rows]

    return UserProfileOut(
        user_id=user.user_id,
        username=user.username,
        full_name=user.full_name,
        email=user.email,
        picture_url=user.picture_url,
        roles=roles,
        factories=[
            FactoryBriefSchema(factory_id=f.factory_id, factory_name=f.factory_name)
            for f in factory_rows
        ],
        factory_access=[
            FactoryAccessEntry(factory_id=fid, access_level=lvl) for fid, lvl in access_rows
        ],
        job_positions=job_positions,
        has_password=bool(user.password_hash),
        privacy_policy_accepted_at=user.privacy_policy_accepted_at,
        privacy_policy_version=user.privacy_policy_version,
        created_at=user.created_at,
        is_super_admin=bool(user.is_super_admin),
    )


async def _active_user_from_principal(session: AsyncSession, p: Principal) -> User:
    try:
        user_id = uuid.UUID(p.user_id)
    except ValueError as exc:
        raise HTTPException(401, "invalid token subject") from exc
    user = await session.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(401, "user not found or inactive")
    return user


def _profile_picture_url(user_id: uuid.UUID) -> str:
    version = int(datetime.now(timezone.utc).timestamp())
    return f"/api/v1/auth/profile-picture/{user_id}?v={version}"


def _profile_image_storage_uri(key: str) -> str:
    if (settings.storage_backend or "local").lower() == "s3":
        return build_s3_uri(settings.s3_bucket, key)
    path = key_to_local_path(
        key,
        documents_dir=settings.documents_dir,
        machines_dir=settings.machines_dir,
        feedback_dir=settings.feedback_dir,
        profile_images_dir=settings.profile_images_dir,
        chat_attachments_dir=settings.chat_attachments_dir,
    )
    return build_file_uri(path)


def _image_signature_matches(mime: str, data: bytes) -> bool:
    if mime == "image/jpeg":
        return data.startswith(b"\xff\xd8")
    if mime == "image/png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    if mime == "image/webp":
        return len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    return False


async def _read_profile_image_upload(file: UploadFile) -> tuple[bytes, str]:
    guessed = guess_image_mime_from_name(file.filename or "")
    mime = (file.content_type or guessed or "").split(";", 1)[0].strip().lower()
    if not is_allowed_image_mime(mime):
        raise HTTPException(415, "profile picture must be JPG, PNG, or WebP")

    limit = settings.max_profile_image_bytes
    data = await file.read(limit + 1)
    if len(data) > limit:
        max_mb = max(1, round(limit / 1024 / 1024))
        raise HTTPException(413, f"profile picture must be {max_mb} MB or smaller")
    if len(data) < 16 or not _image_signature_matches(mime, data):
        raise HTTPException(422, "profile picture content does not match its image type")
    return data, mime


async def _profile_image_uri_for_user(user_id: uuid.UUID) -> tuple[str, str] | None:
    storage = get_storage()
    for mime in _PROFILE_IMAGE_MIMES:
        key = profile_image_object_key(user_id=user_id, mime=mime)
        storage_uri = _profile_image_storage_uri(key)
        if await storage.exists(storage_uri):
            return storage_uri, mime
    return None


@router.get("/me", response_model=UserProfileOut)
async def get_my_profile(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> UserProfileOut:
    """Return the authenticated user's profile and access summary."""
    user = await _active_user_from_principal(session, get_principal(request))
    return await _user_profile_response(session, user)


@router.patch("/me", response_model=TokenResponse, responses=WRITE_ERRORS)
async def update_my_profile(
    payload: UserProfileUpdate,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    """Update self-service profile fields (display name, email, job position)."""
    p = get_principal(request)
    user = await _active_user_from_principal(session, p)

    if payload.full_name is not None:
        user.full_name = payload.full_name.strip()

    if payload.email is not None:
        if user.google_id:
            raise HTTPException(400, "Google accounts sync email from Google")
        email = payload.email.strip().lower()
        if not _EMAIL_RE.match(email):
            raise HTTPException(422, "invalid email address")
        existing = await session.scalar(
            select(User).where(
                func.lower(User.email) == email,
                User.user_id != user.user_id,
            )
        )
        if existing is not None:
            raise HTTPException(409, "email is already in use")
        user.email = email

    if payload.job_position_id is not None:
        if "admin" in p.roles:
            raise HTTPException(400, "admin accounts do not use job positions")
        await set_user_job_positions(session, user, [payload.job_position_id])

    if (
        payload.full_name is None
        and payload.email is None
        and payload.job_position_id is None
    ):
        raise HTTPException(422, "no fields to update")

    await bump_user_token_version(session, user)
    await session.commit()
    await session.refresh(user)
    return await _token_response_for_user(session, user)


@router.post("/me/profile-picture", response_model=TokenResponse, responses=WRITE_ERRORS)
async def upload_my_profile_picture(
    request: Request,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    user = await _active_user_from_principal(session, get_principal(request))
    data, mime = await _read_profile_image_upload(file)

    key = profile_image_object_key(user_id=user.user_id, mime=mime)
    storage = get_storage()
    await storage.put_object(
        key,
        io.BytesIO(data),
        content_type=mime,
        metadata={"user-id": str(user.user_id), "kind": "profile-picture"},
    )

    user.picture_url = _profile_picture_url(user.user_id)
    await bump_user_token_version(session, user)
    await session.commit()
    await session.refresh(user)
    return await _token_response_for_user(session, user)


@router.delete("/me/profile-picture", response_model=TokenResponse, responses=WRITE_ERRORS)
async def delete_my_profile_picture(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    user = await _active_user_from_principal(session, get_principal(request))
    storage = get_storage()
    for mime in _PROFILE_IMAGE_MIMES:
        key = profile_image_object_key(user_id=user.user_id, mime=mime)
        storage_uri = _profile_image_storage_uri(key)
        try:
            await storage.delete(storage_uri)
        except Exception as exc:
            log.debug("profile_picture_delete_skip", user_id=str(user.user_id), error=str(exc)[:120])

    user.picture_url = None
    await bump_user_token_version(session, user)
    await session.commit()
    await session.refresh(user)
    return await _token_response_for_user(session, user)


@router.get("/profile-picture/{user_id}")
async def stream_profile_picture(
    user_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    p = get_principal(request)
    if str(user_id) != p.user_id and not p.is_admin:
        raise HTTPException(403, "cannot view this profile picture")
    user = await session.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(404, "profile picture not found")
    found = await _profile_image_uri_for_user(user_id)
    if found is None:
        raise HTTPException(404, "profile picture not found")
    storage_uri, mime = found
    return StreamingResponse(
        open_storage_object_async(storage_uri),
        media_type=mime,
        headers={"Cache-Control": "private, max-age=300"},
    )


@router.post("/change-password", response_model=TokenResponse, responses=WRITE_ERRORS)
async def change_my_password(
    payload: ChangePasswordRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    """Change password for accounts that use username/password login."""
    user = await _active_user_from_principal(session, get_principal(request))
    if not user.password_hash:
        raise HTTPException(400, "this account uses Google sign-in; password cannot be changed here")

    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(401, "current password is incorrect")

    user.password_hash = hash_password(payload.new_password)
    await bump_user_token_version(session, user)
    await session.commit()
    await session.refresh(user)
    return await _token_response_for_user(session, user)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(401, "missing bearer token")
    token = auth.split(" ", 1)[1].strip()
    body = verify_token(token)
    p = principal_from_token(token)

    try:
        user_id = uuid.UUID(p.user_id)
    except ValueError as exc:
        raise HTTPException(401, "invalid token subject") from exc

    if not await token_version_matches(session, user_id, int(body.get("token_version", 0))):
        raise HTTPException(401, "token expired or revoked")

    user = await session.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(401, "user not found or inactive")
    return await _token_response_for_user(session, user)
