from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.database import get_db
from app.models.cart import CartItem
from app.models.user import User
from app.schemas.cart import CartItemCreate, CartItemUpdate, CartItemOut, CartOut

router = APIRouter()


def _normalize_variant(label: str | None) -> str:
    return (label or "").strip()


def serialize_cart(items: list[CartItem]) -> CartOut:
    outs = [CartItemOut.model_validate(i) for i in items]
    item_count = sum(i.quantity for i in items)
    checkout_ready = len(items) > 0 and all(i.unit_price is not None for i in items)
    subtotal = None
    if checkout_ready:
        subtotal = float(sum((i.unit_price or 0) * i.quantity for i in items))
    return CartOut(items=outs, item_count=item_count, subtotal=subtotal, checkout_ready=checkout_ready)


@router.get("/cart", response_model=CartOut)
def get_cart(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    items = db.query(CartItem).filter(CartItem.user_id == current_user.id).order_by(CartItem.id).all()
    return serialize_cart(items)


@router.post("/cart/items", response_model=CartItemOut)
def add_cart_item(
    body: CartItemCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    variant = _normalize_variant(body.variant_label)
    existing = (
        db.query(CartItem)
        .filter(
            CartItem.user_id == current_user.id,
            CartItem.product_id == body.product_id,
            CartItem.variant_label == variant,
        )
        .first()
    )
    if existing:
        existing.quantity += body.quantity
        existing.subject = body.subject
        existing.unit_price = body.unit_price
        existing.image_url = body.image_url
        existing.category_name = body.category_name or ""
        db.commit()
        db.refresh(existing)
        return existing

    item = CartItem(
        user_id=current_user.id,
        product_id=body.product_id,
        subject=body.subject,
        unit_price=body.unit_price,
        image_url=body.image_url,
        category_name=body.category_name or "",
        variant_label=variant,
        quantity=body.quantity,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.patch("/cart/items/{item_id}", response_model=CartItemOut)
def update_cart_item(
    item_id: int,
    body: CartItemUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    item = (
        db.query(CartItem)
        .filter(CartItem.id == item_id, CartItem.user_id == current_user.id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cart item not found")
    item.quantity = body.quantity
    db.commit()
    db.refresh(item)
    return item


@router.delete("/cart/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_cart_item(
    item_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    item = (
        db.query(CartItem)
        .filter(CartItem.id == item_id, CartItem.user_id == current_user.id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cart item not found")
    db.delete(item)
    db.commit()
    return None
