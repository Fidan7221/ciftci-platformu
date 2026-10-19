"""Sepet modelleri (carts, cart_items tabloları). Akışı Hafta 7'de yazılacak."""
from app.extensions import db
from app.models.base import BaseModel


class Cart(BaseModel):
    __tablename__ = "carts"

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)

    user = db.relationship("User", back_populates="cart")
    items = db.relationship("CartItem", back_populates="cart", cascade="all, delete-orphan")

    @property
    def total(self):
        return sum((item.subtotal for item in self.items), 0)


class CartItem(BaseModel):
    __tablename__ = "cart_items"
    __table_args__ = (
        # Aynı ilan sepete ikinci kez eklenmez; miktarı artırılır
        db.UniqueConstraint("cart_id", "listing_id", name="uq_cart_listing"),
        db.CheckConstraint("quantity > 0", name="ck_cart_item_quantity_positive"),
    )

    cart_id = db.Column(db.Integer, db.ForeignKey("carts.id"), nullable=False)
    listing_id = db.Column(db.Integer, db.ForeignKey("listings.id"), nullable=False, index=True)
    quantity = db.Column(db.Numeric(10, 2), nullable=False)

    cart = db.relationship("Cart", back_populates="items")
    listing = db.relationship("Listing", back_populates="cart_items")

    @property
    def subtotal(self):
        return self.quantity * self.listing.price
