"""管理者・職員の認証・認可（stdlib のみ）。

- パスワード／PINは PBKDF2 でハッシュし、平文を保存しない。
- 秘密鍵はローカルファイルに自動生成（ソース埋め込みなし）。
- 管理者が1人もいない間は導入のため開放モード（既存ローカル運用・テスト互換）。
- 管理者が作成されたあとは、管理APIは管理者セッション必須。
- 職員ポータルは本人セッション（職員ID＋PIN）必須。URLの職員ID改ざんを拒否。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
from pathlib import Path
from typing import Any

from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse

from db.database import DB_PATH, get_connection

AUTH_COOKIE = "shift_mgr_session"
STAFF_COOKIE = "shift_mgr_staff"
SECRET_FILE_NAME = ".auth_secret"
PBKDF2_ITERATIONS = 200_000
SESSION_TTL_SECONDS = 60 * 60 * 12  # 12時間


def _secret_path() -> Path:
    env = os.environ.get("SHIFT_MANAGER_SECRET_FILE")
    if env:
        return Path(env)
    return Path(DB_PATH).resolve().parent / SECRET_FILE_NAME


def get_or_create_secret() -> bytes:
    path = _secret_path()
    if path.exists():
        data = path.read_bytes().strip()
        if data:
            return data
    secret = secrets.token_bytes(32)
    path.write_bytes(secret)
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return secret


def hash_secret(value: str, *, salt: bytes | None = None) -> str:
    if not value:
        raise ValueError("パスワード／PINを入力してください。")
    salt_bytes = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        value.encode("utf-8"),
        salt_bytes,
        PBKDF2_ITERATIONS,
    )
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt_bytes.hex()}${digest.hex()}"


def verify_secret(value: str, encoded: str | None) -> bool:
    if not value or not encoded:
        return False
    try:
        algo, iterations, salt_hex, digest_hex = encoded.split("$", 3)
    except ValueError:
        return False
    if algo != "pbkdf2_sha256":
        return False
    try:
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
        rounds = int(iterations)
    except ValueError:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", value.encode("utf-8"), salt, rounds)
    return hmac.compare_digest(digest, expected)


def ensure_auth_tables(conn: sqlite3.Connection | None = None) -> None:
    owns = conn is None
    if owns:
        conn = get_connection()
    assert conn is not None
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS admin_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            display_name TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    columns = {row[1] for row in conn.execute("PRAGMA table_info(staff)").fetchall()}
    if "portal_pin_hash" not in columns:
        conn.execute("ALTER TABLE staff ADD COLUMN portal_pin_hash TEXT")
    if owns:
        conn.commit()
        conn.close()


def admin_count() -> int:
    ensure_auth_tables()
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS c FROM admin_users").fetchone()
    return int(row["c"] if row else 0)


def auth_enforced() -> bool:
    return admin_count() > 0


def create_admin(username: str, password: str, display_name: str = "") -> dict:
    username = str(username or "").strip()
    display_name = str(display_name or "").strip() or username
    if len(username) < 2 or len(username) > 40:
        raise ValueError("ユーザー名は2〜40文字にしてください。")
    if len(password) < 8:
        raise ValueError("パスワードは8文字以上にしてください。")
    ensure_auth_tables()
    password_hash = hash_secret(password)
    with get_connection() as conn:
        try:
            cursor = conn.execute(
                """
                INSERT INTO admin_users (username, password_hash, display_name)
                VALUES (?, ?, ?)
                """,
                (username, password_hash, display_name),
            )
            conn.commit()
            admin_id = cursor.lastrowid
        except sqlite3.IntegrityError as exc:
            raise ValueError("このユーザー名は既に使われています。") from exc
    return {"id": admin_id, "username": username, "display_name": display_name}


def authenticate_admin(username: str, password: str) -> dict | None:
    ensure_auth_tables()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, username, password_hash, display_name FROM admin_users WHERE username = ? COLLATE NOCASE",
            (str(username or "").strip(),),
        ).fetchone()
    if row is None or not verify_secret(password, row["password_hash"]):
        return None
    return {
        "id": row["id"],
        "username": row["username"],
        "display_name": row["display_name"] or row["username"],
        "role": "admin",
    }


def set_staff_portal_pin(staff_id: int, pin: str | None) -> None:
    ensure_auth_tables()
    pin = None if pin is None else str(pin).strip()
    if pin == "":
        pin_hash = None
    else:
        if not pin.isdigit() or not (4 <= len(pin) <= 8):
            raise ValueError("職員PINは4〜8桁の数字にしてください。")
        pin_hash = hash_secret(pin)
    with get_connection() as conn:
        cursor = conn.execute(
            "UPDATE staff SET portal_pin_hash = ? WHERE id = ?",
            (pin_hash, staff_id),
        )
        if cursor.rowcount == 0:
            raise ValueError("職員が見つかりません。")
        conn.commit()


def authenticate_staff(staff_id: int, pin: str) -> dict | None:
    ensure_auth_tables()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, name, portal_pin_hash FROM staff WHERE id = ?",
            (staff_id,),
        ).fetchone()
    if row is None or not row["portal_pin_hash"]:
        return None
    if not verify_secret(pin, row["portal_pin_hash"]):
        return None
    return {"id": row["id"], "name": row["name"], "role": "staff"}


def _sign_payload(payload: dict) -> str:
    import base64

    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    raw = base64.urlsafe_b64encode(body.encode("utf-8")).decode("ascii").rstrip("=")
    sig = hmac.new(get_or_create_secret(), raw.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{raw}.{sig}"


def _unsign_payload(token: str | None) -> dict | None:
    if not token or "." not in token:
        return None
    import base64

    raw, sig = token.rsplit(".", 1)
    expected = hmac.new(get_or_create_secret(), raw.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None
    pad = "=" * (-len(raw) % 4)
    try:
        body = base64.urlsafe_b64decode(raw + pad).decode("utf-8")
        payload = json.loads(body)
    except (ValueError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    exp = payload.get("exp")
    if not isinstance(exp, (int, float)) or exp < time.time():
        return None
    return payload


def issue_session(subject: dict, *, ttl: int = SESSION_TTL_SECONDS) -> str:
    payload = {
        "role": subject["role"],
        "id": subject["id"],
        "name": subject.get("display_name") or subject.get("name") or subject.get("username"),
        "username": subject.get("username"),
        "exp": int(time.time()) + ttl,
    }
    return _sign_payload(payload)


def read_session(request: Request, cookie_name: str = AUTH_COOKIE) -> dict | None:
    return _unsign_payload(request.cookies.get(cookie_name))


def current_admin(request: Request) -> dict | None:
    payload = read_session(request, AUTH_COOKIE)
    if not payload or payload.get("role") != "admin":
        return None
    return payload


def current_staff(request: Request) -> dict | None:
    payload = read_session(request, STAFF_COOKIE)
    if not payload or payload.get("role") != "staff":
        return None
    return payload


def require_admin(request: Request) -> dict | None:
    """管理API用。管理者が未作成なら開放モードで None を返す。"""
    if not auth_enforced():
        return None
    admin = current_admin(request)
    if admin is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="管理者としてログインしてください。",
        )
    return admin


def require_staff_self(request: Request, staff_id: int) -> dict:
    """ポータルAPI用。セッションの職員IDと一致必須。"""
    staff = current_staff(request)
    if staff is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="職員ログインが必要です。",
        )
    if int(staff.get("id") or 0) != int(staff_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="他の職員の情報にはアクセスできません。",
        )
    return staff


def admin_login_redirect(request: Request) -> RedirectResponse | None:
    if not auth_enforced():
        return None
    if current_admin(request):
        return None
    next_path = request.url.path
    if request.url.query:
        next_path = f"{next_path}?{request.url.query}"
    return RedirectResponse(url=f"/login?next={next_path}", status_code=303)


def setup_needed() -> bool:
    return admin_count() == 0
