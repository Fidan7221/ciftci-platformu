"""Ürün ve kategori sorguları (Hafta 6)."""
from sqlalchemy import func

from app.extensions import db
from app.models import Category, Listing, OrderItem, Product
from app.repositories.base_repository import BaseRepository


class ProductRepository(BaseRepository):
    model = Product

    @staticmethod
    def get_for_producer(product_id, producer_id):
        """Ürünü yalnızca bu üreticiye aitse döndürür; değilse None."""
        return db.session.execute(
            db.select(Product).filter_by(id=product_id, producer_id=producer_id)
        ).scalar_one_or_none()

    @staticmethod
    def paginate_for_producer(producer_id, search=None, category_id=None, page=1, per_page=12):
        stmt = db.select(Product).filter_by(producer_id=producer_id)
        if search:
            stmt = stmt.where(Product.name.ilike(f"%{search}%"))
        if category_id:
            stmt = stmt.where(Product.category_id == category_id)
        stmt = stmt.order_by(Product.created_at.desc(), Product.id.desc())
        return db.paginate(stmt, page=page, per_page=per_page, error_out=False)

    @staticmethod
    def stats_for_producer(producer_id, low_stock_threshold):
        """Panel kartları için özet sayılar (tek tek döngü yerine SQL ile sayılır)."""
        base = db.select(func.count(Product.id)).filter_by(producer_id=producer_id)
        total = db.session.execute(base).scalar()
        active = db.session.execute(base.where(Product.is_active.is_(True))).scalar()
        low_stock = db.session.execute(
            base.where(Product.is_active.is_(True), Product.stock_quantity <= low_stock_threshold)
        ).scalar()
        return {"total": total, "active": active, "low_stock": low_stock}

    @staticmethod
    def recent_for_producer(producer_id, limit=5):
        return db.session.execute(
            db.select(Product).filter_by(producer_id=producer_id)
            .order_by(Product.created_at.desc(), Product.id.desc()).limit(limit)
        ).scalars().all()

    @staticmethod
    def has_orders(product_id):
        """Bu ürünün herhangi bir ilanı siparişe girmiş mi?"""
        count = db.session.execute(
            db.select(func.count(OrderItem.id))
            .join(Listing, OrderItem.listing_id == Listing.id)
            .where(Listing.product_id == product_id)
        ).scalar()
        return count > 0


class CategoryRepository(BaseRepository):
    model = Category

    @staticmethod
    def get_top_level():
        return db.session.execute(
            db.select(Category).filter_by(parent_id=None).order_by(Category.name)
        ).scalars().all()

    @staticmethod
    def get_by_slug(slug):
        return db.session.execute(
            db.select(Category).filter_by(slug=slug)
        ).scalar_one_or_none()

    @staticmethod
    def product_count(category_id):
        return db.session.execute(
            db.select(func.count(Product.id)).filter_by(category_id=category_id)
        ).scalar()
