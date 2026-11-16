from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.cart import CartItemCreate, CartItemUpdate, CartItemOut, CartOut
from app.services.commerce import (
    CommerceError,
    add_cart_item as add_cart_item_service,
    delete_cart_item as delete_cart_item_service,
    get_cart_for_user,
    update_cart_item as update_cart_item_service,
)

router = APIRouter()


def _raise(err: CommerceError) -> None:
    raise HTTPException(status_code=err.status_code, detail=err.detail)


@router.get("/cart", response_model=CartOut)
def get_cart(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return get_cart_for_user(db, current_user.id)


@router.post("/cart/items", response_model=CartItemOut)
def add_cart_item(
    body: CartItemCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return add_cart_item_service(db, current_user.id, body)
    except CommerceError as err:
        _raise(err)


@router.patch("/cart/items/{item_id}", response_model=CartItemOut)
def update_cart_item(
    item_id: int,
    body: CartItemUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return update_cart_item_service(db, current_user.id, item_id, body.quantity)
    except CommerceError as err:
        _raise(err)


@router.delete("/cart/items/{item_id}", status_code=204)
def delete_cart_item(
    item_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        delete_cart_item_service(db, current_user.id, item_id)
    except CommerceError as err:
        _raise(err)
    return None
