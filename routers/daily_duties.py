from datetime import date
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from services.auth import require_admin
from services.daily_duties import get_sheet, save_duty, save_roles, DutyConflict

router = APIRouter(prefix='/api/daily-duties', tags=['デイリー役割表'], dependencies=[Depends(require_admin)])


class DutyUpdate(BaseModel):
    staff_id: int = Field(ge=1)
    date: date
    am: str = Field(default='', max_length=40)
    pm: str = Field(default='', max_length=40)
    signature: str = Field(min_length=64, max_length=64)
    revision: int = Field(ge=0)


class RoleUpdate(BaseModel):
    labels: list[Annotated[str, Field(max_length=40)]] = Field(max_length=100)
    revision: int = Field(ge=1)


@router.get('')
def sheet(start: date, days: int = Query(default=7, ge=1, le=7), floor: str = Query(default='', max_length=20)):
    if not 2000 <= start.year <= 2099:
        raise HTTPException(400, '2000年〜2099年の日付を選択してください。')
    return get_sheet(start, days, floor)


@router.put('/cell')
def update_cell(data: DutyUpdate):
    try:
        return save_duty(data.staff_id, data.date, data.am, data.pm, data.signature, data.revision)
    except DutyConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.put('/roles')
def update_roles(data: RoleUpdate):
    try:
        return save_roles(data.labels, data.revision)
    except DutyConflict as exc:
        raise HTTPException(409, str(exc)) from exc
