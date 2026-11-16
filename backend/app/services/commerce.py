from sqlalchemy.orm import Session

from app.models.cart import CartItem
from app.models.order import Order, OrderItem
from app.schemas.cart import CartItemCreate, CartItemOut, CartOut
from app.schemas.order import OrderCreate


class CommerceError(Exception):
    def __init__(self, detail: str, status_code: int = 400):
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


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


def get_cart_for_user(db: Session, user_id: int) -> CartOut:
    items = db.query(CartItem).filter(CartItem.user_id == user_id).order_by(CartItem.id).all()
    return serialize_cart(items)


def add_cart_item(db: Session, user_id: int, body: CartItemCreate) -> CartItem:
    if body.quantity < 1:
        raise CommerceError("quantity must be >= 1", 400)
    variant = _normalize_variant(body.variant_label)
    existing = (
        db.query(CartItem)
        .filter(
            CartItem.user_id == user_id,
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
        user_id=user_id,
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


def update_cart_item(db: Session, user_id: int, item_id: int, quantity: int) -> CartItem:
    if quantity < 1:
        raise CommerceError("quantity must be >= 1", 400)
    item = (
        db.query(CartItem)
        .filter(CartItem.id == item_id, CartItem.user_id == user_id)
        .first()
    )
    if not item:
        raise CommerceError("Cart item not found", 404)
    item.quantity = quantity
    db.commit()
    db.refresh(item)
    return item


def delete_cart_item(db: Session, user_id: int, item_id: int) -> None:
    item = (
        db.query(CartItem)
        .filter(CartItem.id == item_id, CartItem.user_id == user_id)
        .first()
    )
    if not item:
        raise CommerceError("Cart item not found", 404)
    db.delete(item)
    db.commit()


def create_order_from_cart(db: Session, user_id: int, body: OrderCreate) -> Order:
    items = db.query(CartItem).filter(CartItem.user_id == user_id).all()
    if not items:
        raise CommerceError("Cart is empty", 400)
    if any(i.unit_price is None for i in items):
        raise CommerceError("Cart has items without price", 400)

    total = float(sum((i.unit_price or 0) * i.quantity for i in items))
    order = Order(
        user_id=user_id,
        status="pending",
        recipient_name=body.recipient_name.strip(),
        phone=body.phone.strip(),
        address=body.address.strip(),
        note=(body.note.strip() if body.note else None),
        total_amount=total,
    )
    db.add(order)
    db.flush()
    for item in items:
        db.add(
            OrderItem(
                order_id=order.id,
                product_id=item.product_id,
                subject=item.subject,
                unit_price=float(item.unit_price),
                image_url=item.image_url,
                category_name=item.category_name or "",
                variant_label=item.variant_label or "",
                quantity=item.quantity,
            )
        )
        db.delete(item)
    db.commit()
    db.refresh(order)
    _ = order.items
    return order
