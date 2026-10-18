"""Yapay zekâ tahmin kayıtları (price_predictions tablosu). Hafta 10'da dolduruldu.

Her satır: "Şu ürün için, şu modelle, şu hedef gün için yapılan tahmin".
Aynı ürün + model + hedef gün için tekrar tahmin yapılırsa satır güncellenir (servis katmanında upsert).
"""
from app.extensions import db
from app.models.base import BaseModel


class Trend:
    UP = "up"
    DOWN = "down"
    STABLE = "stable"

    ALL = (UP, DOWN, STABLE)

    LABELS = {UP: "Artış", DOWN: "Düşüş", STABLE: "Dengeli"}
    ICONS = {UP: "arrow-up-right", DOWN: "arrow-down-right", STABLE: "arrow-right"}


class PricePrediction(BaseModel):
    __tablename__ = "price_predictions"

    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False, index=True)
    model_name = db.Column(db.String(50), nullable=False)  # örn. "linreg-30g-v1"
    predicted_price = db.Column(db.Numeric(10, 2), nullable=False)
    target_date = db.Column(db.Date, nullable=False)
    trend = db.Column(db.String(10), nullable=False)
    confidence = db.Column(db.Float)                # 0-1 arası güven skoru
    recommendation = db.Column(db.String(255))      # öneri başlığı

    # --- Hafta 10'da eklenen alanlar (migration gerekir) ---
    current_price = db.Column(db.Numeric(10, 2))        # tahmin anındaki hal seviyesi (son 7 gün ort.)
    lower_price = db.Column(db.Numeric(10, 2))          # %95 tahmin aralığı alt sınırı
    upper_price = db.Column(db.Numeric(10, 2))          # %95 tahmin aralığı üst sınırı
    suggested_min_price = db.Column(db.Numeric(10, 2))  # önerilen satış fiyatı bandı
    suggested_price = db.Column(db.Numeric(10, 2))
    suggested_max_price = db.Column(db.Numeric(10, 2))
    action = db.Column(db.String(20))                   # wait / sell_now / neutral / low_confidence
    backtest_mape = db.Column(db.Float)                 # geri test hatası (0.05 = %5)

    product = db.relationship("Product", back_populates="predictions")

    @property
    def trend_label(self):
        return Trend.LABELS.get(self.trend, self.trend)
