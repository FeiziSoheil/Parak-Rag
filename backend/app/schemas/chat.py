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


class ProductVariantAttribute(BaseModel):
    name: str | None = None
    value: str | None = None


class ProductVariant(BaseModel):
    image: str | None = None
    price: float | None = None
    attributes: list[ProductVariantAttribute] | None = None


class ProductSummary(BaseModel):
    product_id: int
    subject: str
    price: float | None
    image_url: str | None = None
    category_name: str = ""
    variants: list[ProductVariant] | None = None


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


class MessageSearchResult(BaseModel):
    """One message hit when searching across sessions."""

    message_id: int
    session_id: int
    session_title: str
    role: str
    content_snippet: str
    created_at: datetime
