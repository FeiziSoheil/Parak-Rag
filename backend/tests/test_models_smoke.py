from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models import User, CartItem, Order, OrderItem  # noqa: F401


def test_cart_order_tables_create():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    user = User(username="u1", password_hash="x")
    db.add(user)
    db.commit()
    db.refresh(user)
    item = CartItem(
        user_id=user.id,
        product_id=42,
        subject="Widget",
        unit_price=9.99,
        image_url=None,
        category_name="Gadgets",
        variant_label="",
        quantity=2,
    )
    db.add(item)
    db.commit()
    assert db.query(CartItem).count() == 1
    db.close()
