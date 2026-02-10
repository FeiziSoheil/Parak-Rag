import json
from datetime import datetime
from pydantic import BaseModel, field_validator


class SessionCreate(BaseModel):
    title: str | None = "New Chat"


class SessionResponse(BaseModel):
    id: int
    title: str
    created_at: datetime

    class Config:
        from_attributes = True


class MessageIn(BaseModel):
    session_id: int
    message: str
    # image handled via multipart


class ProductSummary(BaseModel):
    product_id: int
    subject: str
    price: float | None
    image_url: str | None = None
    category_name: str = ""


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    image_url: str | None = None
    products: list[ProductSummary] | None = None
    created_at: datetime

    class Config:
        from_attributes = True

    @field_validator("products", mode="before")
    @classmethod
    def parse_products(cls, v):
        if v is None or v == "":
            return None
        if isinstance(v, str):
            try:
                raw = json.loads(v)
                return [ProductSummary(**p) if isinstance(p, dict) else p for p in raw] if raw else None
            except Exception:
                return None
        return v
