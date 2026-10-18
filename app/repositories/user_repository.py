"""Kullanıcı ve rol sorguları."""
from app.extensions import db
from app.models import Role, User
from app.repositories.base_repository import BaseRepository


class UserRepository(BaseRepository):
    model = User

    @staticmethod
    def get_by_email(email):
        return db.session.execute(
            db.select(User).filter_by(email=email)
        ).scalar_one_or_none()

    @staticmethod
    def email_exists(email):
        return UserRepository.get_by_email(email) is not None


class RoleRepository(BaseRepository):
    model = Role

    @staticmethod
    def get_by_name(name):
        return db.session.execute(
            db.select(Role).filter_by(name=name)
        ).scalar_one_or_none()
