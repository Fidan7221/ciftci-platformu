"""Tüm modellerin ortak alanları.

Her tabloda id, created_at ve updated_at sütunları olsun diye
modeller bu sınıftan kalıtım alır (BaseModel).
"""
from datetime import datetime, timezone

from app.extensions import db


def utcnow():
    return datetime.now(timezone.utc)


class BaseModel(db.Model):
    __abstract__ = True  # Bu sınıf için tablo oluşturulmaz

    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    def __repr__(self):
        return f"<{self.__class__.__name__} id={self.id}>"
