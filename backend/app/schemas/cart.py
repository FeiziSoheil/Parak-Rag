from pydantic import BaseModel, Field


class CartItemCreate(BaseModel):
    product_id: int
    subject: str
    unit_price: float | None = None
    image_url: str | None = None
    category_name: str = ""
    variant_label: str = ""
    quantity: int = Field(default=1, ge=1)


class CartItemUpdate(BaseModel):
    quantity: int = Field(ge=1)


class CartItemOut(BaseModel):
    id: int
    product_id: int
    subject: str
    unit_price: float | None
    image_url: str | None
    category_name: str
    variant_label: str
    quantity: int

    model_config = {"from_attributes": True}


class CartOut(BaseModel):
    items: list[CartItemOut]
    item_count: int
    subtotal: float | None
    checkout_ready: bool
