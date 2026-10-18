"""Değerlendirme modeli (reviews tablosu). İtibar hesabı Hafta 11'de yazılacak.

Yorum sipariş kalemine bağlıdır: yalnızca satın alınmış ürün
değerlendirilebilir ve her kalem için tek yorum yapılabilir.
"""
from app.extensions import db
from app.models.base import BaseModel


class Review(BaseModel):
    __tablename__ = "reviews"
    __table_args__ = (
        db.CheckConstraint("rating BETWEEN 1 AND 5", name="ck_review_rating_range"),
    )

    order_item_id = db.Column(
        db.Integer, db.ForeignKey("order_items.id"), unique=True, nullable=False
    )
    customer_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    producer_id = db.Column(
        db.Integer, db.ForeignKey("producer_profiles.id"), nullable=False, index=True
    )
    rating = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.Text)
    is_visible = db.Column(db.Boolean, default=True, nullable=False)  # yönetici gizleyebilir

    order_item = db.relationship("OrderItem", back_populates="review")
    customer = db.relationship("User", back_populates="reviews")
    producer = db.relationship("ProducerProfile", back_populates="reviews")
