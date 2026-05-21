import base64
import hashlib
import hmac

from psycopg import AsyncConnection
from psycopg.rows import dict_row

from memory.postgres import get_postgres_connection_string, validate_postgres_config

PASSWORD_ITERATIONS = 210_000


def _verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, iterations, salt_b64, digest_b64 = password_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
        actual = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            int(iterations),
        )
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


async def setup_users_table() -> None:
    await _setup_postgres_users_table()


async def authenticate_user(username: str, password: str) -> dict | None:
    normalized_username = username.strip().lower()
    user = await _get_postgres_user(normalized_username)
    if not user or not _verify_password(password, user["password_hash"]):
        return None
    return {"id": user["id"], "username": user["username"]}


async def _setup_postgres_users_table() -> None:
    validate_postgres_config()
    async with await AsyncConnection.connect(
        get_postgres_connection_string(),
        autocommit=True,
    ) as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL
            )
            """
        )


async def _get_postgres_user(username: str) -> dict | None:
    async with await AsyncConnection.connect(
        get_postgres_connection_string(),
        row_factory=dict_row,
    ) as conn:
        result = await conn.execute(
            "SELECT id, username, password_hash FROM users WHERE username = %s",
            (username,),
        )
        return await result.fetchone()
