from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
from app.server.database.database import Base

class FurnitureAsset(Base):
    __tablename__="furniture_assets"
    id=Column(Integer, primary_key=True, index=True)
    asset_id=Column(Integer, ForeignKey("assets.asset_id"), nullable=False, unique=True)
    furniture_type=Column(String(100), nullable=False)
    brand=Column(String(100), nullable=True)
    model=Column(String(100), nullable=True)
    material=Column(String(100), nullable=True)
    color=Column(String(50), nullable=True)
    dimensions=Column(String(100), nullable=True)
    asset=relationship("Asset", back_populates="furniture_details")
