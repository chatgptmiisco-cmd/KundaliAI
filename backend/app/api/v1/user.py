from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.base import get_db
from app.db.models.user import User
from app.schemas.user import BirthDataIn, UserProfileOut
from app.services import user_service

router = APIRouter(prefix="/user", tags=["user"])


@router.get("/profile", response_model=UserProfileOut)
async def get_profile(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await user_service.get_user_profile(db, user)


@router.put("/profile/birth-data", response_model=UserProfileOut)
async def update_birth_data(
    body: BirthDataIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    await user_service.upsert_birth_profile(db, user.id, body)
    return await user_service.get_user_profile(db, user)


@router.delete("/account", status_code=204)
async def delete_account(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await user_service.delete_account(db, user.id)
