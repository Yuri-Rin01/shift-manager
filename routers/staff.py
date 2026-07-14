from fastapi import APIRouter, HTTPException, status

from data.masters import validate_staff_for_facility, validate_staffing_basis
from db import staff_repository as repo
from schemas.staff import StaffBulkUpdate, StaffBulkUpdateResponse, StaffCreate, StaffResponse, StaffUpdate

router = APIRouter(prefix="/api/staff", tags=["職員マスタ"])


def _validate_staff(job_type: str, departments: list[str], staffing_basis: dict[str, int]) -> None:
    try:
        validate_staff_for_facility(job_type, departments)
        validate_staffing_basis(staffing_basis)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("", response_model=list[StaffResponse])
def list_staff():
    return repo.list_staff()


@router.post("/bulk", response_model=StaffBulkUpdateResponse)
def bulk_update_staff(data: StaffBulkUpdate):
    fields_set = data.model_fields_set - {"ids", "departments_mode"}
    if not fields_set:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="変更する項目を1つ以上指定してください。",
        )

    sample = repo.get_staff(data.ids[0])
    if sample is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="職員が見つかりません")

    job_type = data.job_type if data.job_type is not None else sample["job_type"]
    departments = (
        data.departments
        if data.departments is not None
        else sample["departments"]
    )
    staffing_basis = (
        data.staffing_basis if data.staffing_basis is not None else sample["staffing_basis"]
    )

    if "job_type" in fields_set or "departments" in fields_set or "staffing_basis" in fields_set:
        _validate_staff(job_type, departments, staffing_basis)

    try:
        updated, not_found = repo.bulk_update_staff(data)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if not updated and not_found:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="職員が見つかりません")

    return StaffBulkUpdateResponse(updated=len(updated), staff=updated, not_found=not_found)


@router.get("/{staff_id}", response_model=StaffResponse)
def get_staff(staff_id: int):
    staff = repo.get_staff(staff_id)
    if staff is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="職員が見つかりません")
    return staff


def _validate_incompatibilities(
    staff_id: int | None,
    incompatible_ids: list[int],
    *,
    label: str,
) -> None:
    if not incompatible_ids:
        return

    if staff_id is not None and staff_id in incompatible_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"自分自身を{label}の対象に指定できません",
        )

    all_staff = repo.get_all_staff_ids()
    invalid = [other_id for other_id in incompatible_ids if other_id not in all_staff]
    if invalid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"存在しない職員が{label}に含まれています",
        )


@router.post("", response_model=StaffResponse, status_code=status.HTTP_201_CREATED)
def create_staff(data: StaffCreate):
    _validate_staff(data.job_type, data.departments, data.staffing_basis)
    _validate_incompatibilities(None, data.night_incompatible_ids, label="夜勤相性")
    _validate_incompatibilities(None, data.day_incompatible_ids, label="日勤相性")
    return repo.create_staff(data)


@router.put("/{staff_id}", response_model=StaffResponse)
def update_staff(staff_id: int, data: StaffUpdate):
    current = repo.get_staff(staff_id)
    if current is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="職員が見つかりません")

    job_type = data.job_type if data.job_type is not None else current["job_type"]
    departments = data.departments if data.departments is not None else current["departments"]
    staffing_basis = (
        data.staffing_basis if data.staffing_basis is not None else current["staffing_basis"]
    )
    _validate_staff(job_type, departments, staffing_basis)
    night_ids = (
        data.night_incompatible_ids
        if data.night_incompatible_ids is not None
        else current["night_incompatible_ids"]
    )
    day_ids = (
        data.day_incompatible_ids
        if data.day_incompatible_ids is not None
        else current["day_incompatible_ids"]
    )
    _validate_incompatibilities(staff_id, night_ids, label="夜勤相性")
    _validate_incompatibilities(staff_id, day_ids, label="日勤相性")
    staff = repo.update_staff(staff_id, data)
    if staff is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="職員が見つかりません")
    return staff


@router.delete("/{staff_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_staff(staff_id: int):
    deleted = repo.delete_staff(staff_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="職員が見つかりません")
