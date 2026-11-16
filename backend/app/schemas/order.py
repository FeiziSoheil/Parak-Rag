from datetime import datetime

from pydantic import BaseModel, Field


class OrderCreate(BaseModel):
    recipient_name: str = Field(min_length=1)
    phone: str = Field(min_length=1)
    address: str = Field(min_length=1)
    note: str | None = None


class OrderItemOut(BaseModel):
    id: int
    product_id: int
    subject: str
    unit_price: float
    image_url: str | None
    category_name: str
    variant_label: str
    quantity: int

    model_config = {"from_attributes": True}


class OrderOut(BaseModel):
    id: int
    status: str
    recipient_name: str
    phone: str
    address: str
    note: str | None
    total_amount: float
    created_at: datetime
    items: list[OrderItemOut]

    model_config = {"from_attributes": True}
