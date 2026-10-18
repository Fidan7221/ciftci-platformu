"""Ödeme modeli (payments tablosu). Ödeme API'si Hafta 9'da bağlanacak."""
from app.extensions import db
from app.models.base import BaseModel


class PaymentStatus:
    INITIATED = "initiated"
    SUCCESS = "success"
    FAILED = "failed"
    REFUNDED = "refunded"

    ALL = (INITIATED, SUCCESS, FAILED, REFUNDED)


class Payment(BaseModel):
    __tablename__ = "payments"

    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), unique=True, nullable=False)
    provider = db.Column(db.String(30), nullable=False)       # örn. "mock", "iyzico"
    transaction_ref = db.Column(db.String(100), unique=True)  # sağlayıcının işlem numarası
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    status = db.Column(db.String(20), default=PaymentStatus.INITIATED, nullable=False)
    paid_at = db.Column(db.DateTime(timezone=True))
    error_message = db.Column(db.String(255))

    order = db.relationship("Order", back_populates="payment")
