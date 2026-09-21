"""バックアップ・復元 API。"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from services import backup as backup_service

router = APIRouter(prefix="/api/backup", tags=["バックアップ"])


@router.get("")
def list_backups():
    return {"items": backup_service.list_backups()}


@router.post("/create")
def create_backup(note: str = Form(default="")):
    try:
        result = backup_service.create_backup(note=note.strip(), prefix="manual")
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"バックアップに失敗しました: {exc}",
        ) from exc
    return result


@router.get("/download/{filename}")
def download_backup(filename: str):
    try:
        path = backup_service.resolve_backup_filename(filename)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ファイルが見つかりません")
    return FileResponse(
        path,
        filename=path.name,
        media_type="application/zip",
    )


@router.post("/validate")
async def validate_uploaded_backup(file: UploadFile = File(...)):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix != ".zip":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ZIP形式のバックアップファイルを選んでください。",
        )
    backup_service.ensure_backup_dir()
    with tempfile.NamedTemporaryFile(
        prefix="upload-", suffix=".zip", dir=backup_service.BACKUP_ROOT, delete=False
    ) as tmp:
        tmp_path = Path(tmp.name)
        shutil.copyfileobj(file.file, tmp)
    try:
        summary = backup_service.validate_backup_file(tmp_path)
        # 検証用に残す（復元時に同じファイル名で参照）
        stored_name = f"upload-pending-{Path(tmp_path).stem[-8:]}-{Path(file.filename or 'backup').stem[:20]}.zip"
        # 一意な保存名
        from datetime import datetime, timedelta, timezone

        jst = timezone(timedelta(hours=9))
        stored_name = f"upload-pending-{datetime.now(jst).strftime('%Y%m%d-%H%M%S')}.zip"
        stored = backup_service.BACKUP_ROOT / stored_name
        tmp_path.replace(stored)
        summary["pending_filename"] = stored_name
        return summary
    except ValueError as exc:
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


@router.post("/restore")
def restore_backup(
    filename: str = Form(...),
    confirm: bool = Form(False),
):
    try:
        path = backup_service.resolve_backup_filename(filename)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ファイルが見つかりません")
    try:
        return backup_service.restore_backup(path, confirm=confirm)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
