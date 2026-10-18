"""Tüm repository sınıflarının ortak CRUD işlemleri.

Repository katmanı, veri tabanına erişen TEK katmandır.
Servisler doğrudan db.session kullanmaz; buradaki metotları çağırır.
"""
from app.extensions import db


class BaseRepository:
    model = None  # Alt sınıf hangi modelle çalıştığını belirtir

    @classmethod
    def get_by_id(cls, obj_id):
        return db.session.get(cls.model, obj_id)

    @classmethod
    def get_all(cls):
        return db.session.execute(db.select(cls.model)).scalars().all()

    @staticmethod
    def add(obj):
        db.session.add(obj)
        return obj

    @staticmethod
    def delete(obj):
        db.session.delete(obj)

    @staticmethod
    def commit():
        db.session.commit()

    @staticmethod
    def rollback():
        db.session.rollback()

    @staticmethod
    def expire(obj):
        """Nesnenin alanları bir sonraki erişimde veri tabanından yeniden okunur."""
        db.session.expire(obj)
