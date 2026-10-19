"""Rapor sorguları (Hafta 12).

Raporun tüm verisi TEK sorguyla gelir: dönemdeki sipariş kalemleri + sipariş, müşteri, üretici, ürün ve
kategori bilgisi (JOIN). Nesne (ORM modeli) değil yalnızca gereken sütunlar seçilir; böylece:
- N+1 olmaz (her kalem için ürün/kategori ayrıca sorgulanmaz),
- bellek kullanımı düşük kalır (binlerce Order/Product nesnesi oluşturulmaz).
"""
from sqlalchemy.orm import aliased

from app.extensions import db
from app.models import Category, Listing, Order, OrderItem, ProducerProfile, Product, User
from app.reports.builder import ReportRow


class ReportRepository:

    @staticmethod
    def order_item_rows(start_utc, end_utc, producer_id=None, limit=None):
        """[start_utc, end_utc) aralığındaki siparişlerin kalemleri.

        producer_id verilirse yalnızca o üreticinin kalemleri gelir. Üretici raporunda bu değer
        her zaman oturumdaki kullanıcının profilinden alınır, URL'den ASLA (IDOR koruması).
        """
        customer = aliased(User)
        stmt = (
            db.select(Order.id, Order.created_at, Order.status, Order.customer_id, customer.full_name,
                      OrderItem.producer_id, ProducerProfile.farm_name, Product.id, Product.name,
                      Product.unit, Category.name, OrderItem.quantity, OrderItem.unit_price)
            .select_from(OrderItem)
            .join(Order, OrderItem.order_id == Order.id)
            .join(customer, Order.customer_id == customer.id)
            .join(ProducerProfile, OrderItem.producer_id == ProducerProfile.id)
            .join(Listing, OrderItem.listing_id == Listing.id)
            .join(Product, Listing.product_id == Product.id)
            .join(Category, Product.category_id == Category.id)
            .where(Order.created_at >= start_utc, Order.created_at < end_utc)
            .order_by(Order.created_at, Order.id, OrderItem.id)
        )
        if producer_id is not None:
            stmt = stmt.where(OrderItem.producer_id == producer_id)
        if limit is not None:
            stmt = stmt.limit(limit)
        return [ReportRow(*row) for row in db.session.execute(stmt).all()]

    @staticmethod
    def producers():
        """Yöneticinin rapor filtresindeki üretici listesi."""
        return db.session.execute(
            db.select(ProducerProfile.id, ProducerProfile.farm_name).order_by(ProducerProfile.farm_name)
        ).all()

    @staticmethod
    def get_producer(producer_id):
        return db.session.get(ProducerProfile, producer_id)
