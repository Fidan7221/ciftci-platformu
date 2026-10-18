"""Yapay zekâ tahmin kayıtlarının sorguları (Hafta 10)."""
from sqlalchemy import func

from app.extensions import db
from app.models import PricePrediction
from app.repositories.base_repository import BaseRepository


class PredictionRepository(BaseRepository):
    model = PricePrediction

    @staticmethod
    def find(product_id, model_name, target_date):
        return db.session.execute(
            db.select(PricePrediction).filter_by(product_id=product_id, model_name=model_name,
                                                 target_date=target_date)
        ).scalar_one_or_none()

    @staticmethod
    def latest_for_product(product_id, model_name):
        return db.session.execute(
            db.select(PricePrediction).filter_by(product_id=product_id, model_name=model_name)
            .order_by(PricePrediction.target_date.desc(), PricePrediction.id.desc()).limit(1)
        ).scalar_one_or_none()

    @staticmethod
    def count():
        return db.session.execute(db.select(func.count(PricePrediction.id))).scalar()
