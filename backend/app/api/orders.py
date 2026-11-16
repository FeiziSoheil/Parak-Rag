from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.database import get_db
from app.models.cart import CartItem
from app.models.order import Order, OrderItem
from app.models.user import User
from app.schemas.order import OrderCreate, OrderOut

router = APIRouter()


@router.post("/orders", response_model=OrderOut)
def create_order(
    body: OrderCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    items = db.query(CartItem).filter(CartItem.user_id == current_user.id).all()
    if not items:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cart is empty")
    if any(i.unit_price is None for i in items):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cart has items without price",
        )

    total = float(sum((i.unit_price or 0) * i.quantity for i in items))
    order = Order(
        user_id=current_user.id,
        status="pending",
        recipient_name=body.recipient_name.strip(),
        phone=body.phone.strip(),
        address=body.address.strip(),
        note=(body.note.strip() if body.note else None),
        total_amount=total,
    )
    db.add(order)
    db.flush()

    for i in items:
        db.add(
            OrderItem(
                order_id=order.id,
                product_id=i.product_id,
                subject=i.subject,
                unit_price=float(i.unit_price),
                image_url=i.image_url,
                category_name=i.category_name or "",
                variant_label=i.variant_label or "",
                quantity=i.quantity,
            )
        )
        db.delete(i)

    db.commit()
    db.refresh(order)
    _ = order.items
    return order
