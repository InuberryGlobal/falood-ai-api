import os
import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import HTTPException
from jwt_service import create_access_token

def get_db_connection():
    return psycopg2.connect(os.getenv("DATABASE_URL"))


def upsert_session_details(user_id: str, company: str, position: str):
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    INSERT INTO session_details (user_id, company, position)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (user_id) 
                    DO UPDATE SET 
                        company = EXCLUDED.company,
                        position = EXCLUDED.position
                    RETURNING id, user_id, company, position
                """, (user_id, company, position))
                row = cur.fetchone()
                conn.commit()

        return {
            "session_details_id": str(row["id"]),
            "user_id": str(row["user_id"]),
            "company": row["company"],
            "position": row["position"]
        }
    except Exception:
        raise HTTPException(status_code=500, detail="Database error")


def get_all_sessions(user_id: str):
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, company, position, created_at
                    FROM sessions
                    WHERE user_id = %s
                    ORDER BY created_at DESC
                    """,
                    (user_id,),
                )
                rows = cur.fetchall() or []

        return [
            {
                "session_id": str(r["id"]),
                "company": r.get("company") or "",
                "position": r.get("position") or "",
                "created_at": (
                    r["created_at"].isoformat() if r.get("created_at") else None
                ),
            }
            for r in rows
        ]
    except Exception:
        raise HTTPException(status_code=500, detail="Database error")


def create_session(user_id: str):
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT company, position FROM session_details WHERE user_id = %s",
                    (user_id,)
                )
                row = cur.fetchone()
                if not row:
                    raise HTTPException(status_code=400, detail="Session details are missing")

                company = row["company"]
                position = row["position"]

                # 2) Insert a new session (denormalized with company/position)
                cur.execute(
                    """
                    INSERT INTO sessions (user_id, company, position)
                    VALUES (%s, %s, %s)
                    RETURNING id
                    """,
                    (user_id, company, position),
                )
                inserted = cur.fetchone()
                conn.commit()

        return { "session_id": str(inserted["id"]) }

    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Database error")


def get_session_details(user_id: str):
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT id, user_id, company, position FROM session_details WHERE user_id = %s",
                    (user_id,)
                )
                row = cur.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Session details not found")

        return {
            "session_details_id": str(row["id"]),
            "user_id": str(row["user_id"]),
            "company": row["company"],
            "position": row["position"]
        }
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Database error")


def get_one_session_details(session_id: str):
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, user_id, company, position, created_at, ended_at
                    FROM sessions
                    WHERE id = %s
                    """,
                    (session_id,),
                )
                row = cur.fetchone()

                if not row:
                    raise HTTPException(status_code=404, detail="Session details not found")

                cur.execute(
                    """
                    SELECT id, question, response, created_at
                    FROM session_conversations
                    WHERE session_id = %s
                    ORDER BY created_at ASC
                    """,
                    (session_id,),
                )
                conv_rows = cur.fetchall() or []

        return {
            "session_details_id": str(row["id"]),
            "user_id": str(row["user_id"]),
            "company": row["company"],
            "position": row["position"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            "ended_at": row["ended_at"].isoformat() if row["ended_at"] else None,
            "conversations": [
                {
                    "id": str(c["id"]),
                    "question": c["question"],
                    "response": c["response"],
                    "created_at": c["created_at"].isoformat() if c["created_at"] else None,
                }
                for c in conv_rows
            ],
        }
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Database error")
