import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import jwt
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pwdlib import PasswordHash
from pydantic import BaseModel

load_dotenv()

DATABASE_PATH = os.getenv("DATABASE_PATH", "legacydoc.db")
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "legacydoc-dev-secret-do-not-use-in-production")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "60"))
MIN_PASSWORD_LENGTH = int(os.getenv("MIN_PASSWORD_LENGTH", "8"))

password_hash = PasswordHash.recommended()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


class UserRegister(BaseModel):
    email: str
    password: str


class UserLogin(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class CurrentUser(BaseModel):
    id: int
    email: str


def normalize_email(email: str) -> str:
    return email.strip().lower()


def validate_credentials_input(email: str, password: str) -> str:
    normalized_email = normalize_email(email)

    if "@" not in normalized_email or "." not in normalized_email.split("@")[-1]:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="E-mail invalido.",
        )

    if len(password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"A senha deve ter pelo menos {MIN_PASSWORD_LENGTH} caracteres.",
        )

    return normalized_email


def get_connection():
    database_parent = Path(DATABASE_PATH).expanduser().resolve().parent
    database_parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DATABASE_PATH)


def init_auth_db():
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def create_user(email: str, password: str) -> CurrentUser:
    normalized_email = validate_credentials_input(email, password)
    hashed_password = password_hash.hash(password)

    try:
        with get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO users (email, password_hash, created_at)
                VALUES (?, ?, ?)
                """,
                (normalized_email, hashed_password, datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()

            return CurrentUser(id=cursor.lastrowid, email=normalized_email)

    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="E-mail ja cadastrado.",
        ) from exc


def get_user_by_email(email: str) -> Optional[dict]:
    normalized_email = normalize_email(email)

    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "SELECT id, email, password_hash FROM users WHERE email = ?",
            (normalized_email,),
        )
        row = cursor.fetchone()

    return dict(row) if row else None


def authenticate_user(email: str, password: str) -> CurrentUser:
    user = get_user_by_email(email)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais invalidas.",
        )

    if not password_hash.verify(password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais invalidas.",
        )

    return CurrentUser(id=user["id"], email=user["email"])


def create_access_token(user: CurrentUser) -> str:
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES)

    payload = {
        "sub": str(user.id),
        "email": user.email,
        "exp": expires_at,
    }

    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def get_current_user(token: str = Depends(oauth2_scheme)) -> CurrentUser:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token invalido ou expirado.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("sub")
        email = payload.get("email")

        if user_id is None or email is None:
            raise credentials_exception

        return CurrentUser(id=int(user_id), email=email)

    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expirado.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    except jwt.InvalidTokenError as exc:
        raise credentials_exception from exc
