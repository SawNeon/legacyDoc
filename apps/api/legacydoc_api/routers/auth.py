"""Rotas de autenticacao e chaves de API."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request, status
from legacydoc_core.db import get_db
from legacydoc_core.email import get_email_sender, render_password_reset
from legacydoc_core.errors import AuthenticationError, ConflictError, NotFoundError
from legacydoc_core.models import ApiKey, PasswordResetToken, User
from legacydoc_core.plans import get_plan
from legacydoc_core.security import (
    MAX_FAILED_LOGINS,
    RESET_TOKEN_TTL_MINUTES,
    create_access_token,
    generate_api_key,
    generate_reset_token,
    hash_password,
    hash_reset_token,
    is_locked,
    lockout_until,
    normalize_email,
    validate_email,
    validate_password_strength,
    verify_password,
)
from legacydoc_core.settings import Settings
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from legacydoc_api.deps import (
    Principal,
    count_jobs_this_month,
    get_app_settings,
    get_principal,
    spend_this_month,
)
from legacydoc_api.schemas import (
    ApiKeyCreatedResponse,
    ApiKeyCreateRequest,
    ApiKeyResponse,
    LoginRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
    PlanInfo,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> TokenResponse:
    email = validate_email(payload.email)
    validate_password_strength(payload.password, settings.min_password_length)

    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        display_name=payload.display_name,
        plan_tier="free",
    )
    session.add(user)

    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise ConflictError("E-mail ja cadastrado.") from exc

    return _token_for(user, settings)


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> TokenResponse:
    email = normalize_email(payload.email)
    user = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()

    # Identical response for unknown email and wrong password: any difference
    # here becomes an account enumeration oracle.
    if user is None:
        raise AuthenticationError("Credenciais invalidas.")

    # Checked before verifying the password, otherwise an attacker keeps
    # testing candidates and is only stopped afterwards.
    if is_locked(user.locked_until):
        raise AuthenticationError(
            "Conta temporariamente bloqueada por tentativas seguidas de login. "
            "Tente novamente mais tarde ou redefina sua senha."
        )

    if not verify_password(payload.password, user.password_hash):
        user.failed_login_attempts += 1
        user.locked_until = lockout_until(user.failed_login_attempts)

        remaining_attempts = MAX_FAILED_LOGINS - user.failed_login_attempts

        # Explicit commit before raising: the session rolls back on exception, so
        # the attempt counter would never persist and lockout would never trigger.
        await session.commit()

        if user.locked_until is not None:
            raise AuthenticationError(
                "Conta temporariamente bloqueada por tentativas seguidas de login."
            )

        # The remaining count is never revealed: it would confirm the email exists.
        logger.info("Failed login for %s; %d attempt(s) before lockout.", email, remaining_attempts)
        raise AuthenticationError("Credenciais invalidas.")

    if not user.is_active:
        raise AuthenticationError("Conta desativada.")

    user.failed_login_attempts = 0
    user.locked_until = None

    return _token_for(user, settings)


@router.get("/me", response_model=UserResponse)
async def me(
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_db),
) -> UserResponse:
    used = await count_jobs_this_month(session, principal.id)
    spent = await spend_this_month(session, principal.id)

    return UserResponse(
        id=principal.user.id,
        email=principal.user.email,
        display_name=principal.user.display_name,
        plan=_plan_info(principal.user.plan_tier),
        jobs_used_this_month=used,
        spent_this_month_usd=round(spent, 4),
    )


@router.post("/password-reset/request", status_code=status.HTTP_202_ACCEPTED)
async def request_password_reset(
    payload: PasswordResetRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> dict[str, str]:
    """Send the reset link when the account exists.

    Always answers 202 with the same message whether or not the email is known;
    saying otherwise would turn this endpoint into an account checker.
    """
    email = normalize_email(payload.email)
    user = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()

    if user is not None and user.is_active:
        # Requesting a new link invalidates any previous one.
        await session.execute(
            update(PasswordResetToken)
            .where(
                PasswordResetToken.user_id == user.id,
                PasswordResetToken.used_at.is_(None),
            )
            .values(used_at=datetime.now(UTC))
        )

        generated = generate_reset_token()

        session.add(
            PasswordResetToken(
                user_id=user.id,
                token_hash=generated.token_hash,
                expires_at=generated.expires_at,
                requested_ip=request.client.host if request.client else None,
            )
        )

        frontend = settings.frontend_base_url.rstrip("/")
        reset_url = f"{frontend}/nova-senha?token={generated.plaintext}"
        subject, body = render_password_reset(
            reset_url=reset_url, ttl_minutes=RESET_TOKEN_TTL_MINUTES
        )

        await get_email_sender(settings).send(to=user.email, subject=subject, body=body)

    return {
        "message": (
            "Se houver uma conta com esse e-mail, enviamos um link de redefinicao. "
            "Verifique sua caixa de entrada."
        )
    }


@router.post("/password-reset/confirm", response_model=TokenResponse)
async def confirm_password_reset(
    payload: PasswordResetConfirm,
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> TokenResponse:
    """Set a new password from the emailed token and return a session."""
    validate_password_strength(payload.new_password, settings.min_password_length)

    reset_token = (
        await session.execute(
            select(PasswordResetToken).where(
                PasswordResetToken.token_hash == hash_reset_token(payload.token)
            )
        )
    ).scalar_one_or_none()

    if reset_token is None or reset_token.used_at is not None:
        raise AuthenticationError("Link invalido ou ja utilizado.")

    expires_at = reset_token.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)

    if expires_at <= datetime.now(UTC):
        raise AuthenticationError("Link expirado. Peca um novo.")

    user = await session.get(User, reset_token.user_id)

    if user is None or not user.is_active:
        raise AuthenticationError("Link invalido ou ja utilizado.")

    user.password_hash = hash_password(payload.new_password)

    # Proving email access clears the lockout the attack itself caused.
    user.failed_login_attempts = 0
    user.locked_until = None

    reset_token.used_at = datetime.now(UTC)

    return _token_for(user, settings)


# --------------------------------------------------------------- chaves API


@router.post(
    "/api-keys",
    response_model=ApiKeyCreatedResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_api_key(
    payload: ApiKeyCreateRequest,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_db),
) -> ApiKeyCreatedResponse:
    """Create a long-lived key for the VS Code extension or CI.

    The plaintext exists only in this response; the database stores the hash.
    """
    generated = generate_api_key()

    record = ApiKey(
        user_id=principal.id,
        name=payload.name,
        prefix=generated.prefix,
        key_hash=generated.key_hash,
    )
    session.add(record)
    await session.flush()

    return ApiKeyCreatedResponse(
        id=record.id,
        name=record.name,
        prefix=record.prefix,
        created_at=record.created_at,
        last_used_at=None,
        revoked_at=None,
        api_key=generated.plaintext,
    )


@router.get("/api-keys", response_model=list[ApiKeyResponse])
async def list_api_keys(
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_db),
) -> list[ApiKeyResponse]:
    rows = (
        await session.execute(
            select(ApiKey).where(ApiKey.user_id == principal.id).order_by(ApiKey.created_at.desc())
        )
    ).scalars()

    return [
        ApiKeyResponse(
            id=key.id,
            name=key.name,
            prefix=key.prefix,
            created_at=key.created_at,
            last_used_at=key.last_used_at,
            revoked_at=key.revoked_at,
        )
        for key in rows
    ]


@router.delete("/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(
    key_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_db),
) -> None:
    key = await session.get(ApiKey, key_id)

    if key is None or key.user_id != principal.id:
        raise NotFoundError("Chave nao encontrada.")

    key.revoked_at = datetime.now(UTC)


# ------------------------------------------------------------------ apoio


def _token_for(user: User, settings: Settings) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(str(user.id), user.email, settings),
        expires_in_seconds=settings.jwt_expire_minutes * 60,
    )


def _plan_info(tier: str) -> PlanInfo:
    plan = get_plan(tier)

    return PlanInfo(
        tier=str(plan.tier),
        display_name=plan.display_name,
        monthly_job_quota=plan.monthly_job_quota,
        monthly_cost_limit_usd=plan.monthly_cost_limit_usd,
        max_files_per_job=plan.max_files_per_job,
        max_concurrent_jobs=plan.max_concurrent_jobs,
        features=sorted(str(feature) for feature in plan.features),
        max_depth=str(plan.max_depth),
        available_depths=[str(depth) for depth in plan.available_depths],
    )
