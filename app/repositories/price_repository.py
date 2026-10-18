"""Piyasa fiyatı sorguları (Hafta 9)."""
from sqlalchemy import func

from app.extensions import db
from app.models import MarketPrice
from app.repositories.base_repository import BaseRepository


class PriceRepository(BaseRepository):
    model = MarketPrice

    @staticmethod
    def get_quote(product_name, source, price_date):
        return db.session.execute(
            db.select(MarketPrice).filter_by(product_name=product_name, source=source, price_date=price_date)
        ).scalar_one_or_none()

    @staticmethod
    def latest_date():
        return db.session.execute(db.select(func.max(MarketPrice.price_date))).scalar()

    @staticmethod
    def for_date(day, search=None):
        stmt = db.select(MarketPrice).where(MarketPrice.price_date == day)
        if search:
            stmt = stmt.where(MarketPrice.product_name.ilike(f"%{search}%"))
        return db.session.execute(stmt.order_by(MarketPrice.product_name)).scalars().all()

    @staticmethod
    def latest_for_category(category_id):
        return db.session.execute(
            db.select(MarketPrice).where(MarketPrice.category_id == category_id)
            .order_by(MarketPrice.price_date.desc(), MarketPrice.id.desc()).limit(1)
        ).scalar_one_or_none()

    @staticmethod
    def previous_for(product_name, before_date):
        return db.session.execute(
            db.select(MarketPrice)
            .where(MarketPrice.product_name == product_name, MarketPrice.price_date < before_date)
            .order_by(MarketPrice.price_date.desc()).limit(1)
        ).scalar_one_or_none()

    @staticmethod
    def history(product_name, since):
        return db.session.execute(
            db.select(MarketPrice)
            .where(MarketPrice.product_name == product_name, MarketPrice.price_date >= since)
            .order_by(MarketPrice.price_date)
        ).scalars().all()

    @staticmethod
    def count():
        return db.session.execute(db.select(func.count(MarketPrice.id))).scalar()

    # --- Hafta 10: yapay zekâ modeli için zaman serileri ------------------------------------

    @staticmethod
    def daily_series_for_category(category_id, since):
        """[(tarih, ortalama fiyat), ...] — aynı gün birden çok kaynak varsa ortalaması alınır."""
        rows = db.session.execute(
            db.select(MarketPrice.price_date, func.avg(MarketPrice.avg_price))
            .where(MarketPrice.category_id == category_id, MarketPrice.price_date >= since)
            .group_by(MarketPrice.price_date)
            .order_by(MarketPrice.price_date)
        ).all()
        return [(day, float(price)) for day, price in rows]

    @staticmethod
    def categories_with_prices(since):
        """Fiyat verisi olan kategori id'leri, kayıt sayısına göre çoktan aza."""
        rows = db.session.execute(
            db.select(MarketPrice.category_id, func.count(MarketPrice.id))
            .where(MarketPrice.category_id.is_not(None), MarketPrice.price_date >= since)
            .group_by(MarketPrice.category_id)
            .order_by(func.count(MarketPrice.id).desc(), MarketPrice.category_id)
        ).all()
        return [category_id for category_id, _ in rows]
