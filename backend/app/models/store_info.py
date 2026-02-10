from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func

from app.core.database import Base


class StoreInfo(Base):
    __tablename__ = "store_info"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(String(2000), nullable=True)
    address = Column(String(512), nullable=True)
    working_hours = Column(String(255), nullable=True)
    phone = Column(String(64), nullable=True)
    email = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
