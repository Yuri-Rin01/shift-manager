"""アプリ状態のバックアップと復元（SQLite 整合性を保つ）。"""

from __future__ import annotations

import json
import re
import shutil
import sqlite3
import tempfile
import threading
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from db.database import DB_PATH, BASE_DIR, get_connection, init_db

# バックアップ形式の版。破壊的なスキーマ変更時に上げる。
BACKUP_FORMAT_VERSION = 1
APP_DATA_LABEL = "shift-manager"

BACKUP_ROOT = BASE_DIR / "var" / "backups"
REQUIRED_TABLES = frozenset(
    {
        "staff",
        "app_settings",
        "shift_assignments",
        "staff_floors",
        "leave_requests",
    }
)

_restore_lock = threading.Lock()
_write_blocked = False


def is_write_blocked() -> bool:
    return _write_blocked


def ensure_backup_dir() -> Path:
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    gitignore = BACKUP_ROOT / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text("*\n!.gitignore\n", encoding="utf-8")
    return BACKUP_ROOT


def _jst_stamp() -> str:
    from datetime import timedelta

    jst = timezone(timedelta(hours=9))
    return datetime.now(jst).strftime("%Y%m%d-%H%M%S")


def _table_counts(conn: sqlite3.Connection) -> dict[str, int]:
    names = [
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]
    counts: dict[str, int] = {}
    for name in names:
        quoted = '"' + name.replace('"', '""') + '"'
        counts[name] = int(conn.execute(f"SELECT COUNT(*) FROM {quoted}").fetchone()[0])
    return counts


def _build_manifest(conn: sqlite3.Connection, *, note: str = "") -> dict:
    return {
        "format": "shift-manager-backup",
        "format_version": BACKUP_FORMAT_VERSION,
        "app": APP_DATA_LABEL,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "note": note,
        "source_db": str(DB_PATH.name),
        "tables": _table_counts(conn),
    }


def create_backup(*, note: str = "", prefix: str = "backup") -> dict:
    """現在の DB を zip（db + manifest）として保存する。"""
    ensure_backup_dir()
    stamp = _jst_stamp()
    safe_prefix = re.sub(r"[^\w\-]+", "_", prefix).strip("_") or "backup"
    filename = f"{safe_prefix}_{stamp}.zip"
    dest = BACKUP_ROOT / filename

    with tempfile.TemporaryDirectory(prefix="shift-bak-") as tmp:
        tmp_path = Path(tmp)
        db_copy = tmp_path / "shift.db"
        src = sqlite3.connect(DB_PATH)
        try:
            src.execute("PRAGMA foreign_keys = ON")
            dest_conn = sqlite3.connect(db_copy)
            try:
                src.backup(dest_conn)
                dest_conn.execute("PRAGMA foreign_keys = ON")
                check = dest_conn.execute("PRAGMA integrity_check").fetchone()[0]
                if check != "ok":
                    raise RuntimeError(f"バックアップの整合性チェックに失敗しました: {check}")
                manifest = _build_manifest(dest_conn, note=note)
            finally:
                dest_conn.close()
        finally:
            src.close()

        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.write(db_copy, arcname="shift.db")
            zf.write(manifest_path, arcname="manifest.json")

    return {
        "filename": filename,
        "path": str(dest),
        "created_at": manifest["created_at"],
        "note": note,
        "tables": manifest["tables"],
        "format_version": BACKUP_FORMAT_VERSION,
    }


def list_backups() -> list[dict]:
    ensure_backup_dir()
    items: list[dict] = []
    for path in sorted(BACKUP_ROOT.glob("*.zip"), key=lambda p: p.stat().st_mtime, reverse=True):
        info = {
            "filename": path.name,
            "size_bytes": path.stat().st_size,
            "modified_at": datetime.fromtimestamp(
                path.stat().st_mtime, tz=timezone.utc
            ).isoformat(),
        }
        try:
            with zipfile.ZipFile(path, "r") as zf:
                if "manifest.json" in zf.namelist():
                    manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
                    info["created_at"] = manifest.get("created_at")
                    info["note"] = manifest.get("note") or ""
                    info["tables"] = manifest.get("tables") or {}
                    info["format_version"] = manifest.get("format_version")
        except (OSError, zipfile.BadZipFile, json.JSONDecodeError, UnicodeDecodeError):
            info["invalid"] = True
        items.append(info)
    return items


def _extract_backup_zip(zip_path: Path, dest_dir: Path) -> tuple[Path, dict]:
    with zipfile.ZipFile(zip_path, "r") as zf:
        names = zf.namelist()
        if "shift.db" not in names or "manifest.json" not in names:
            raise ValueError(
                "バックアップ形式が不正です。shift.db と manifest.json が必要です。"
            )
        # Zip Slip 防止
        for name in names:
            target = (dest_dir / name).resolve()
            if not str(target).startswith(str(dest_dir.resolve())):
                raise ValueError("バックアップ内のパスが不正です。")
        zf.extractall(dest_dir)
    db_path = dest_dir / "shift.db"
    manifest = json.loads((dest_dir / "manifest.json").read_text(encoding="utf-8"))
    return db_path, manifest


def validate_backup_file(path: Path) -> dict:
    """アップロード／保存済みバックアップを検証し、要約を返す（DBは変更しない）。"""
    if not path.exists() or not path.is_file():
        raise ValueError("バックアップファイルが見つかりません。")
    if path.suffix.lower() != ".zip":
        raise ValueError("バックアップは .zip 形式である必要があります。")

    with tempfile.TemporaryDirectory(prefix="shift-val-") as tmp:
        tmp_path = Path(tmp)
        try:
            db_path, manifest = _extract_backup_zip(path, tmp_path)
        except zipfile.BadZipFile as exc:
            raise ValueError("ZIPファイルとして開けません。") from exc

        if manifest.get("format") != "shift-manager-backup":
            raise ValueError("このファイルはシフト作成システムのバックアップではありません。")
        version = int(manifest.get("format_version") or 0)
        if version < 1 or version > BACKUP_FORMAT_VERSION:
            raise ValueError(
                f"未対応のバックアップ形式です（version={version}）。"
                f"このアプリが扱えるのは 1〜{BACKUP_FORMAT_VERSION} です。"
            )

        conn = sqlite3.connect(db_path)
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            check = conn.execute("PRAGMA integrity_check").fetchone()[0]
            if check != "ok":
                raise ValueError(f"データベースの整合性チェックに失敗しました: {check}")
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            missing = sorted(REQUIRED_TABLES - tables)
            if missing:
                raise ValueError(
                    "必要なテーブルが不足しています: " + ", ".join(missing)
                )
            counts = _table_counts(conn)
        finally:
            conn.close()

    current = _table_counts(get_connection())
    return {
        "ok": True,
        "filename": path.name,
        "format_version": version,
        "created_at": manifest.get("created_at"),
        "note": manifest.get("note") or "",
        "backup_tables": counts,
        "current_tables": current,
        "overwrite_summary": {
            "staff": {
                "backup": counts.get("staff", 0),
                "current": current.get("staff", 0),
            },
            "shift_assignments": {
                "backup": counts.get("shift_assignments", 0),
                "current": current.get("shift_assignments", 0),
            },
            "shift_placements": {
                "backup": counts.get("shift_placements", 0),
                "current": current.get("shift_placements", 0),
            },
            "leave_requests": {
                "backup": counts.get("leave_requests", 0),
                "current": current.get("leave_requests", 0),
            },
            "app_settings": {
                "backup": counts.get("app_settings", 0),
                "current": current.get("app_settings", 0),
            },
        },
        "warning": (
            "復元すると、いまの職員・勤務表・配置・設定・希望休が"
            "バックアップの内容で置き換わります。"
        ),
    }


def restore_backup(path: Path, *, confirm: bool) -> dict:
    """検証済みバックアップで現行 DB を置き換える。失敗時は現行を壊さない。"""
    if not confirm:
        raise ValueError("復元には確認（confirm=true）が必要です。")

    if not _restore_lock.acquire(blocking=False):
        raise RuntimeError("別の復元処理が実行中です。しばらくしてから再度お試しください。")

    global _write_blocked
    safety: dict | None = None
    try:
        summary = validate_backup_file(path)
        # 復元直前に現行を自動退避
        safety = create_backup(note="復元直前の自動バックアップ", prefix="pre-restore")
        _write_blocked = True

        with tempfile.TemporaryDirectory(prefix="shift-rst-") as tmp:
            tmp_path = Path(tmp)
            db_path, _manifest = _extract_backup_zip(path, tmp_path)

            # 一時場所へ最終コピーしてから原子的に入れ替え
            staged = tmp_path / "staged.db"
            shutil.copy2(db_path, staged)

            # 稼働中接続を切るため、入れ替え前に軽いチェック接続を閉じる
            live_parent = DB_PATH.parent
            live_parent.mkdir(parents=True, exist_ok=True)
            replacement = live_parent / f".restore-{_jst_stamp()}.db"
            shutil.copy2(staged, replacement)

            # Windows でも比較的安全な入れ替え: 退避 → 置換
            previous = live_parent / f".before-restore-{_jst_stamp()}.db"
            if DB_PATH.exists():
                shutil.copy2(DB_PATH, previous)
            try:
                replacement.replace(DB_PATH)
            except OSError:
                # replace 失敗時はコピーで上書きを試す
                shutil.copy2(replacement, DB_PATH)
            finally:
                if replacement.exists():
                    replacement.unlink(missing_ok=True)

        # マイグレーション適用・古い生成プレビューを無効化
        init_db()
        with get_connection() as conn:
            exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='generation_previews'"
            ).fetchone()
            if exists:
                conn.execute("DELETE FROM generation_previews")
            else:
                # テーブルが無い場合も明示的に作って空にしておく（古いトークン適用を防ぐ）
                conn.execute(
                    """CREATE TABLE IF NOT EXISTS generation_previews (
                        token TEXT PRIMARY KEY,
                        expires REAL NOT NULL,
                        fingerprint TEXT NOT NULL,
                        payload TEXT NOT NULL
                    )"""
                )
            conn.commit()

        return {
            "ok": True,
            "restored_from": path.name,
            "safety_backup": safety,
            "summary": summary,
            "message": (
                "復元が完了しました。"
                "古い自動生成プレビューは無効化しました。"
                f"問題があれば「{safety['filename']}」から戻せます。"
            ),
        }
    except Exception:
        # 失敗時は安全バックアップを残し、現行 DB は replace 前なら無変更
        raise
    finally:
        _write_blocked = False
        _restore_lock.release()


def resolve_backup_filename(filename: str) -> Path:
    name = Path(filename).name
    if name != filename or "/" in filename or "\\" in filename:
        raise ValueError("ファイル名が不正です。")
    if not re.fullmatch(r"[\w.\-]+\.zip", name):
        raise ValueError("バックアップファイル名が不正です。")
    path = (BACKUP_ROOT / name).resolve()
    if not str(path).startswith(str(BACKUP_ROOT.resolve())):
        raise ValueError("バックアップの参照先が不正です。")
    return path
