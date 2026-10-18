"""Yapay zekâ tahmin kayıtları (price_predictions tablosu). Hafta 10'da doldurulacak."""
from app.extensions import db
from app.models.base import BaseModel


class Trend:
    UP = "up"
    DOWN = "down"
    STABLE = "stable"

    ALL = (UP, DOWN, STABLE)


class PricePrediction(BaseModel):
    __tablename__ = "price_predictions"

    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False, index=True)
    model_name = db.Column(db.String(50), nullable=False)  # örn. "linear_regression_v1"
    predicted_price = db.Column(db.Numeric(10, 2), nullable=False)
    target_date = db.Column(db.Date, nullable=False)
    trend = db.Column(db.String(10), nullable=False)
    confidence = db.Column(db.Float)                # 0-1 arası güven skoru
    recommendation = db.Column(db.String(255))      # örn. "Fiyat yükseliyor, 1 hafta bekleyin"

    product = db.relationship("Product", back_populates="predictions")
