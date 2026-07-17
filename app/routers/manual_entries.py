from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.manual_entry import ManualEntryBatch, ManualEntryUpdateResult
from app.services.manual_entry_service import upsert_manual_entries
from app.services.profile_service import ProfileNotFoundError

router = APIRouter(tags=["manual-entries"])


@router.post("/update-manual-entry", response_model=ManualEntryUpdateResult)
def update_manual_entry(
    payload: ManualEntryBatch,
    db: Annotated[Session, Depends(get_db)],
) -> ManualEntryUpdateResult:
    try:
        return upsert_manual_entries(db, payload)
    except ProfileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
