"""Piyasa fiyat geçmişi (market_prices tablosu).

Harici fiyat API'sinden (Hafta 9) gelen günlük fiyatlar burada birikir.
Yapay zekâ bileşeni (Hafta 10) trend tahminini bu verilerle yapar.
"""
from app.extensions import db
from app.models.base import BaseModel


class MarketPrice(BaseModel):
    __tablename__ = "market_prices"
    __table_args__ = (
        # Aynı ürünün aynı kaynaktan aynı güne ait fiyatı iki kez kaydedilmez
        db.UniqueConstraint("product_name", "source", "price_date", name="uq_market_price_day"),
    )

    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"))
    product_name = db.Column(db.String(120), nullable=False, index=True)
    source = db.Column(db.String(60), nullable=False)  # örn. "hal_api", "mock"
    unit = db.Column(db.String(10), default="kg", nullable=False)
    min_price = db.Column(db.Numeric(10, 2))
    max_price = db.Column(db.Numeric(10, 2))
    avg_price = db.Column(db.Numeric(10, 2), nullable=False)
    price_date = db.Column(db.Date, nullable=False, index=True)

    category = db.relationship("Category", back_populates="market_prices")
