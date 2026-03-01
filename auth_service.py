import os
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.errors import UniqueViolation
from passlib.context import CryptContext
from fastapi import HTTPException
from jwt_service import create_access_token, verify_token

def get_db_connection():
    return psycopg2.connect(os.getenv("DATABASE_URL"))

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def create_user(email: str, username: str, password: str):
    hashed_password = pwd_context.hash(password)

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO users (email, username, hashed_password)
                    VALUES (%s, %s, %s)
                    RETURNING id
                    """,
                    (email, username, hashed_password),
                )
                user_id = cur.fetchone()[0]
    except UniqueViolation:
        raise HTTPException(status_code=400, detail="Email already registered")
    except Exception:
        raise HTTPException(status_code=500, detail="Database error")

    access_token = create_access_token(
        data={"email": email, "username": username, "user_id": str(user_id)}
    )
    return {"access_token": access_token, "user_id": str(user_id)}


def get_user_by_email(email: str):
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM users WHERE email = %s", (email,))
            row = cur.fetchone()
            return dict(row) if row else None


def _issue_access_token(user: dict) -> dict:
    token = create_access_token(
        data={
            "email": user["email"],
            "username": user["username"],
            "user_id": str(user["id"]),
        }
    )
    return {"access_token": token, "user_id": str(user["id"])}


def sign_in(email: str, password: str) -> dict:
    try:
        user = get_user_by_email(email)
        if not user or not validate_password(password, user["hashed_password"]):
            raise HTTPException(status_code=401, detail="Invalid credentials")
        return _issue_access_token(user)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Database error")


def get_me(token: str) -> dict:
    try:
        payload = verify_token(token)
        user_id = payload.get("user_id")
        email = payload.get("email")
        username = payload.get("username")
        if not user_id or not email:
            raise HTTPException(status_code=403, detail="Invalid token")
        return {"user_id": str(user_id), "username": username, "email": email}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=403, detail="Invalid token")


def validate_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)
