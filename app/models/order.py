"""Sipariş modelleri (orders, order_items tabloları). Akışı Hafta 7'de yazılacak."""
from app.extensions import db
from app.models.base import BaseModel


class OrderStatus:
    PENDING = "pending"        # Oluşturuldu, ödeme bekleniyor
    PAID = "paid"              # Ödendi
    SHIPPED = "shipped"        # Kargoya verildi
    DELIVERED = "delivered"    # Teslim edildi (değerlendirme açılır)
    CANCELLED = "cancelled"    # İptal edildi

    ALL = (PENDING, PAID, SHIPPED, DELIVERED, CANCELLED)

    LABELS = {
        PENDING: "Ödeme bekleniyor",
        PAID: "Ödendi",
        SHIPPED: "Kargoda",
        DELIVERED: "Teslim edildi",
        CANCELLED: "İptal edildi",
    }
    BADGES = {
        PENDING: "text-bg-warning",
        PAID: "text-bg-info",
        SHIPPED: "text-bg-primary",
        DELIVERED: "text-bg-success",
        CANCELLED: "text-bg-secondary",
    }
    # Ekranda gösterilen ilerleme sırası (iptal hariç)
    FLOW = (PENDING, PAID, SHIPPED, DELIVERED)


class Order(BaseModel):
    __tablename__ = "orders"
    __table_args__ = (
        # Hafta 11: "Siparişlerim" sayfası müşteri id'sine göre süzer, tarihe göre sıralar
        db.Index("ix_orders_customer_created_at", "customer_id", "created_at"),
    )

    customer_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    total_amount = db.Column(db.Numeric(10, 2), nullable=False)
    status = db.Column(db.String(20), default=OrderStatus.PENDING, nullable=False, index=True)
    shipping_address = db.Column(db.String(255), nullable=False)
    note = db.Column(db.String(255))

    customer = db.relationship("User", back_populates="orders")
    items = db.relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    payment = db.relationship(
        "Payment", back_populates="order", uselist=False, cascade="all, delete-orphan"
    )

    @property
    def status_label(self):
        return OrderStatus.LABELS.get(self.status, self.status)

    @property
    def status_badge(self):
        return OrderStatus.BADGES.get(self.status, "text-bg-light")

    @property
    def producer(self):
        """Hafta 7'den itibaren her sipariş tek üreticiye aittir (sepet üreticiye göre bölünür)."""
        return self.items[0].producer if self.items else None


class OrderItem(BaseModel):
    __tablename__ = "order_items"
    __table_args__ = (
        db.CheckConstraint("quantity > 0", name="ck_order_item_quantity_positive"),
    )

    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False, index=True)
    listing_id = db.Column(db.Integer, db.ForeignKey("listings.id"), nullable=False, index=True)
    # Çok üreticili sepet: her kalemin hangi üreticiye ait olduğu (raporlar için)
    producer_id = db.Column(
        db.Integer, db.ForeignKey("producer_profiles.id"), nullable=False, index=True
    )
    quantity = db.Column(db.Numeric(10, 2), nullable=False)
    # Sipariş anındaki fiyat DONDURULUR; ilan fiyatı sonra değişse de bu değişmez
    unit_price = db.Column(db.Numeric(10, 2), nullable=False)

    order = db.relationship("Order", back_populates="items")
    listing = db.relationship("Listing", back_populates="order_items")
    producer = db.relationship("ProducerProfile", back_populates="order_items")
    review = db.relationship("Review", back_populates="order_item", uselist=False)

    @property
    def subtotal(self):
        return self.quantity * self.unit_price
