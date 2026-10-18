"""Üretici profili modeli (producer_profiles tablosu).

Her üretici aynı zamanda bir kullanıcıdır (users). Çiftliğe özgü
bilgiler bu tabloda, kullanıcıyla 1-1 ilişkili olarak tutulur.
"""
from app.extensions import db
from app.models.base import BaseModel


class ProducerProfile(BaseModel):
    __tablename__ = "producer_profiles"

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)
    farm_name = db.Column(db.String(120), nullable=False)
    region = db.Column(db.String(80), nullable=False)  # örn. "Bingöl / Genç"
    description = db.Column(db.Text)
    tax_number = db.Column(db.String(20))
    is_verified = db.Column(db.Boolean, default=False, nullable=False)

    # Değerlendirmelerden hesaplanıp önbellek olarak saklanır (Hafta 11)
    reputation_score = db.Column(db.Float, default=0.0, nullable=False)
    review_count = db.Column(db.Integer, default=0, nullable=False)

    # --- İlişkiler ---
    user = db.relationship("User", back_populates="producer_profile")
    products = db.relationship(
        "Product", back_populates="producer", cascade="all, delete-orphan"
    )
    order_items = db.relationship("OrderItem", back_populates="producer")
    reviews = db.relationship("Review", back_populates="producer")

    def __repr__(self):
        return f"<ProducerProfile {self.farm_name}>"
