from fastapi import APIRouter, HTTPException, status

from db import settings_repository as repo
from schemas.settings import AppSettings

router = APIRouter(prefix="/api/settings", tags=["各種設定"])


@router.get("", response_model=AppSettings)
def get_app_settings():
    return repo.get_settings()


@router.get("/defaults", response_model=AppSettings)
def get_default_settings():
    from data.settings_defaults import DEFAULT_SETTINGS

    return DEFAULT_SETTINGS


@router.put("", response_model=AppSettings)
def update_app_settings(data: AppSettings):
    try:
        return repo.save_settings(data.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc