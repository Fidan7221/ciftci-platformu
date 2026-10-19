"""İlan sorguları (Hafta 7)."""
from datetime import date

from sqlalchemy import func, or_
from sqlalchemy.orm import contains_eager

from app.extensions import db
from app.models import Listing, ListingStatus, ProducerProfile, Product
from app.repositories.base_repository import LIKE_ESCAPE, BaseRepository, contains_pattern


def _available_conditions():
    """Müşteriye gösterilecek ilanların SQL koşulları (Listing.is_available ile aynı kural)."""
    today = date.today()
    return (
        Listing.status == ListingStatus.ACTIVE,
        Listing.stock_quantity > 0,
        Listing.start_date <= today,
        or_(Listing.end_date.is_(None), Listing.end_date >= today),
        Product.is_active.is_(True),
    )


class ListingRepository(BaseRepository):
    model = Listing

    @staticmethod
    def get_for_producer(listing_id, producer_id):
        return db.session.execute(
            db.select(Listing).join(Listing.product)
            .where(Listing.id == listing_id, Product.producer_id == producer_id)
        ).scalar_one_or_none()

    @staticmethod
    def paginate_for_producer(producer_id, status=None, page=1, per_page=12):
        stmt = (db.select(Listing).join(Listing.product)
                .options(contains_eager(Listing.product))  # Hafta 11: ürün zaten JOIN'de; ayrı sorgu yok
                .where(Product.producer_id == producer_id))
        if status:
            stmt = stmt.where(Listing.status == status)
        stmt = stmt.order_by(Listing.created_at.desc(), Listing.id.desc())
        return db.paginate(stmt, page=page, per_page=per_page, error_out=False)

    @staticmethod
    def paginate_available(search=None, category_ids=None, page=1, per_page=12):
        stmt = (db.select(Listing).join(Listing.product).join(Product.producer)
                # Hafta 11: JOIN'lenen ürün ve üretici nesnelere doldurulur. Olmasaydı her kart için
                # listing.product ve product.producer ayrı ayrı sorgulanırdı (12 ilan = 24 ek sorgu).
                .options(contains_eager(Listing.product).contains_eager(Product.producer))
                .where(*_available_conditions()))
        if search:
            pattern = contains_pattern(search)
            stmt = stmt.where(or_(Listing.title.ilike(pattern, escape=LIKE_ESCAPE), Product.name.ilike(pattern, escape=LIKE_ESCAPE),
                                  ProducerProfile.farm_name.ilike(pattern, escape=LIKE_ESCAPE)))
        if category_ids:
            stmt = stmt.where(Product.category_id.in_(category_ids))
        stmt = stmt.order_by(Listing.created_at.desc(), Listing.id.desc())
        return db.paginate(stmt, page=page, per_page=per_page, error_out=False)

    @staticmethod
    def active_reserved_quantity(product_id, exclude_listing_id=None):
        """Ürünün AKTİF ilanlarına ayrılmış toplam miktar."""
        stmt = (db.select(func.coalesce(func.sum(Listing.stock_quantity), 0))
                .where(Listing.product_id == product_id, Listing.status == ListingStatus.ACTIVE))
        if exclude_listing_id:
            stmt = stmt.where(Listing.id != exclude_listing_id)
        return db.session.execute(stmt).scalar()
