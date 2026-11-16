from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.order import OrderCreate, OrderOut
from app.services.commerce import CommerceError, create_order_from_cart

router = APIRouter()


@router.post("/orders", response_model=OrderOut)
def create_order(
    body: OrderCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return create_order_from_cart(db, current_user.id, body)
    except CommerceError as err:
        raise HTTPException(status_code=err.status_code, detail=err.detail)
