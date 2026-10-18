"""Ödeme modeli (payments tablosu). Hafta 9'da ödeme sağlayıcısına bağlandı.

Her siparişin tek bir ödeme kaydı vardır; başarısız denemelerden sonra yeni deneme
aynı kaydı günceller (attempt_count artar). Kart bilgisinden yalnızca son 4 hane saklanır.
"""
from app.extensions import db
from app.models.base import BaseModel


class PaymentStatus:
    INITIATED = "initiated"   # Sağlayıcıya gönderildi, sonuç henüz kesin değil (ör. zaman aşımı)
    SUCCESS = "success"
    FAILED = "failed"
    REFUNDED = "refunded"

    ALL = (INITIATED, SUCCESS, FAILED, REFUNDED)

    LABELS = {INITIATED: "Sonuç bekleniyor", SUCCESS: "Başarılı", FAILED: "Başarısız", REFUNDED: "İade edildi"}
    BADGES = {INITIATED: "text-bg-warning", SUCCESS: "text-bg-success",
              FAILED: "text-bg-danger", REFUNDED: "text-bg-secondary"}


class Payment(BaseModel):
    __tablename__ = "payments"

    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), unique=True, nullable=False)
    provider = db.Column(db.String(30), nullable=False)       # "mock", "http", "manual"
    transaction_ref = db.Column(db.String(100), unique=True)  # sağlayıcının işlem numarası
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    status = db.Column(db.String(20), default=PaymentStatus.INITIATED, nullable=False)
    paid_at = db.Column(db.DateTime(timezone=True))
    error_message = db.Column(db.String(255))

    # --- Hafta 9'da eklenen alanlar (migration gerekir) ---
    idempotency_key = db.Column(db.String(64))                # aynı ödemenin iki kez çekilmesini önler
    attempt_count = db.Column(db.Integer, default=0, server_default="0", nullable=False)
    card_last4 = db.Column(db.String(4))                      # yalnızca son 4 hane
    refund_ref = db.Column(db.String(100))
    refunded_at = db.Column(db.DateTime(timezone=True))

    order = db.relationship("Order", back_populates="payment")

    @property
    def status_label(self):
        return PaymentStatus.LABELS.get(self.status, self.status)

    @property
    def status_badge(self):
        return PaymentStatus.BADGES.get(self.status, "text-bg-light")
