"""Satış ilanı modeli (listings tablosu).

Bir ürün farklı dönemlerde farklı fiyat ve stokla ilana çıkabilir.
Sepet ve sipariş kalemleri ürüne değil, ilana bağlanır.

İki stok kuralı (Hafta 7):
- products.stock_quantity  = depodaki toplam miktar
- listings.stock_quantity  = bu ilanla satışa ayrılan miktar
- Bir ürünün AKTİF ilanlarının toplam miktarı, ürün stoğunu aşamaz.
- Sipariş verilince ikisi birlikte düşer, iptalde ikisi birlikte geri eklenir.
"""
from datetime import date

from app.extensions import db
from app.models.base import BaseModel


class ListingStatus:
    ACTIVE = "active"        # Satışta
    SOLD_OUT = "sold_out"    # Stok bitti (sistem otomatik verir)
    CLOSED = "closed"        # Üretici satıştan kaldırdı (pasif)

    ALL = (ACTIVE, SOLD_OUT, CLOSED)

    LABELS = {ACTIVE: "Satışta", SOLD_OUT: "Tükendi", CLOSED: "Pasif"}
    BADGES = {ACTIVE: "text-bg-success", SOLD_OUT: "text-bg-warning", CLOSED: "text-bg-secondary"}


class Listing(BaseModel):
    __tablename__ = "listings"
    __table_args__ = (
        db.CheckConstraint("price >= 0", name="ck_listing_price_positive"),
        db.CheckConstraint("stock_quantity >= 0", name="ck_listing_stock_positive"),
        # Hafta 11: Pazar sorgusu "status = active ... ORDER BY created_at DESC" çalıştırır;
        # bileşik indeks hem süzmeyi hem sıralamayı tek indeksle karşılar.
        db.Index("ix_listings_status_created_at", "status", "created_at"),
    )

    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False, index=True)
    title = db.Column(db.String(150), nullable=False)
    price = db.Column(db.Numeric(10, 2), nullable=False)          # birim fiyatı (TL)
    stock_quantity = db.Column(db.Numeric(10, 2), nullable=False)  # satışa ayrılan miktar
    min_order_quantity = db.Column(db.Numeric(10, 2), default=1, nullable=False)
    start_date = db.Column(db.Date, default=date.today, nullable=False)
    end_date = db.Column(db.Date)
    status = db.Column(db.String(20), default=ListingStatus.ACTIVE, nullable=False, index=True)

    # --- İlişkiler ---
    product = db.relationship("Product", back_populates="listings")
    cart_items = db.relationship("CartItem", back_populates="listing", cascade="all, delete-orphan")
    order_items = db.relationship("OrderItem", back_populates="listing")

    @property
    def is_in_date_range(self):
        today = date.today()
        return self.start_date <= today and (self.end_date is None or self.end_date >= today)

    @property
    def is_available(self):
        """Müşteri bu ilanı şu an satın alabilir mi?"""
        return (
            self.status == ListingStatus.ACTIVE
            and self.stock_quantity > 0
            and self.is_in_date_range
            and self.product is not None
            and self.product.is_active
        )

    @property
    def status_label(self):
        if self.status == ListingStatus.ACTIVE and not self.is_in_date_range:
            return "Süresi dışında"
        return ListingStatus.LABELS.get(self.status, self.status)

    @property
    def producer(self):
        return self.product.producer if self.product else None

    def __repr__(self):
        return f"<Listing {self.title} {self.price} TL>"
