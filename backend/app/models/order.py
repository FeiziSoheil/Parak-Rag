from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    status = Column(String(64), nullable=False, default="pending")
    recipient_name = Column(String(255), nullable=False)
    phone = Column(String(64), nullable=False)
    address = Column(Text, nullable=False)
    note = Column(Text, nullable=True)
    total_amount = Column(Float, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="orders")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False, index=True)
    product_id = Column(Integer, nullable=False)
    subject = Column(String(1024), nullable=False)
    unit_price = Column(Float, nullable=False)
    image_url = Column(String(2048), nullable=True)
    category_name = Column(String(512), nullable=False, default="")
    variant_label = Column(String(512), nullable=False, default="")
    quantity = Column(Integer, nullable=False)

    order = relationship("Order", back_populates="items")
