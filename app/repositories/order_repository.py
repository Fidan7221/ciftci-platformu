"""Sipariş sorguları ve atomik stok güncellemeleri (Hafta 7).

Stok düşürme işlemleri "oku → hesapla → yaz" şeklinde DEĞİL, tek bir koşullu
UPDATE ile yapılır:

    UPDATE listings SET stock_quantity = stock_quantity - :q
    WHERE id = :id AND stock_quantity >= :q AND status = 'active'

Etkilenen satır sayısı 0 ise stok yetmemiştir. Böylece aynı anda gelen iki
sipariş aynı son ürünü satın alamaz (race condition önlenir).
"""
from sqlalchemy import case, func, update

from app.extensions import db
from app.models import Listing, ListingStatus, Order, OrderItem, Product
from app.repositories.base_repository import BaseRepository

# Oturumdaki nesneleri Python tarafında senkronlamaya çalışma; commit sonrası zaten yenilenir
_NO_SYNC = {"synchronize_session": False}


class OrderRepository(BaseRepository):
    model = Order

    # --- Sorgular ---------------------------------------------------------

    @staticmethod
    def paginate_for_customer(customer_id, page=1, per_page=10):
        stmt = (db.select(Order).filter_by(customer_id=customer_id)
                .order_by(Order.created_at.desc(), Order.id.desc()))
        return db.paginate(stmt, page=page, per_page=per_page, error_out=False)

    @staticmethod
    def paginate_for_producer(producer_id, status=None, page=1, per_page=10):
        stmt = (db.select(Order)
                .where(Order.id.in_(db.select(OrderItem.order_id)
                                    .where(OrderItem.producer_id == producer_id)))
                .order_by(Order.created_at.desc(), Order.id.desc()))
        if status:
            stmt = stmt.where(Order.status == status)
        return db.paginate(stmt, page=page, per_page=per_page, error_out=False)

    @staticmethod
    def producer_has_items(order_id, producer_id):
        return db.session.execute(
            db.select(func.count(OrderItem.id))
            .where(OrderItem.order_id == order_id, OrderItem.producer_id == producer_id)
        ).scalar() > 0

    @staticmethod
    def transition_status(order_id, from_status, to_status):
        """Durumu yalnızca sipariş HÂLÂ from_status durumundaysa değiştirir.

        Aynı siparişe aynı anda iki "iptal" isteği gelirse yalnızca biri başarılı olur;
        böylece stok iki kez geri eklenmez.
        """
        result = db.session.execute(
            update(Order)
            .where(Order.id == order_id, Order.status == from_status)
            .values(status=to_status)
            .execution_options(**_NO_SYNC)
        )
        return result.rowcount == 1

    # --- Atomik stok işlemleri -----------------------------------------------

    @staticmethod
    def decrease_listing_stock(listing_id, quantity):
        """Stok yeterliyse düşürür ve True döner; yetmiyorsa hiçbir şey yapmaz, False döner."""
        result = db.session.execute(
            update(Listing)
            .where(Listing.id == listing_id,
                   Listing.status == ListingStatus.ACTIVE,
                   Listing.stock_quantity >= quantity)
            .values(stock_quantity=func.round(Listing.stock_quantity - quantity, 2))
            .execution_options(**_NO_SYNC)
        )
        return result.rowcount == 1

    @staticmethod
    def decrease_product_stock(product_id, quantity):
        result = db.session.execute(
            update(Product)
            .where(Product.id == product_id, Product.stock_quantity >= quantity)
            .values(stock_quantity=func.round(Product.stock_quantity - quantity, 2))
            .execution_options(**_NO_SYNC)
        )
        return result.rowcount == 1

    @staticmethod
    def mark_sold_out(listing_ids):
        """Stoğu sıfıra inen ilanları 'Tükendi' yapar."""
        db.session.execute(
            update(Listing)
            .where(Listing.id.in_(listing_ids), Listing.stock_quantity <= 0,
                   Listing.status == ListingStatus.ACTIVE)
            .values(status=ListingStatus.SOLD_OUT)
            .execution_options(**_NO_SYNC)
        )

    @staticmethod
    def restore_stock(listing_id, product_id, quantity):
        """İptalde stokları geri ekler; tükenmiş ilan tekrar satışa açılır."""
        db.session.execute(
            update(Listing)
            .where(Listing.id == listing_id)
            .values(
                stock_quantity=func.round(Listing.stock_quantity + quantity, 2),
                status=case((Listing.status == ListingStatus.SOLD_OUT, ListingStatus.ACTIVE),
                            else_=Listing.status),
            )
            .execution_options(**_NO_SYNC)
        )
        db.session.execute(
            update(Product)
            .where(Product.id == product_id)
            .values(stock_quantity=func.round(Product.stock_quantity + quantity, 2))
            .execution_options(**_NO_SYNC)
        )


class StatsRepository:
    """Paneller için özet sayılar (Hafta 8). Sayım SQL'de yapılır, kayıtlar belleğe çekilmez."""

    @staticmethod
    def count(model, *conditions):
        stmt = db.select(func.count(model.id))
        if conditions:
            stmt = stmt.where(*conditions)
        return db.session.execute(stmt).scalar()

    @staticmethod
    def producer_order_count(producer_id, statuses):
        return db.session.execute(
            db.select(func.count(Order.id))
            .where(Order.status.in_(statuses),
                   Order.id.in_(db.select(OrderItem.order_id).where(OrderItem.producer_id == producer_id)))
        ).scalar()

    @staticmethod
    def revenue(statuses):
        return db.session.execute(
            db.select(func.coalesce(func.sum(Order.total_amount), 0)).where(Order.status.in_(statuses))
        ).scalar()

    @staticmethod
    def recent_orders_for_customer(customer_id, limit=3):
        return db.session.execute(
            db.select(Order).filter_by(customer_id=customer_id)
            .order_by(Order.created_at.desc(), Order.id.desc()).limit(limit)
        ).scalars().all()

    @staticmethod
    def paginate_all_orders(status=None, page=1, per_page=15):
        stmt = db.select(Order).order_by(Order.created_at.desc(), Order.id.desc())
        if status:
            stmt = stmt.where(Order.status == status)
        return db.paginate(stmt, page=page, per_page=per_page, error_out=False)
