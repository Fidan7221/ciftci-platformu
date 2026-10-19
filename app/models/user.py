"""Kullanıcı ve rol modelleri (roles, users tabloları)."""
from flask_login import UserMixin
from sqlalchemy.orm import joinedload
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db, login_manager
from app.models.base import BaseModel


class RoleName:
    """Rol adlarını sabit olarak tutar; kodda "producer" yazım hatası yapılmasını önler."""

    ADMIN = "admin"
    PRODUCER = "producer"
    CUSTOMER = "customer"

    ALL = (ADMIN, PRODUCER, CUSTOMER)


class Role(BaseModel):
    __tablename__ = "roles"

    name = db.Column(db.String(20), unique=True, nullable=False)
    description = db.Column(db.String(120))

    users = db.relationship("User", back_populates="role")

    def __repr__(self):
        return f"<Role {self.name}>"


class User(UserMixin, BaseModel):
    __tablename__ = "users"

    role_id = db.Column(db.Integer, db.ForeignKey("roles.id"), nullable=False, index=True)
    full_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    phone = db.Column(db.String(20))
    city = db.Column(db.String(50))
    address = db.Column(db.String(255))
    is_active_account = db.Column(db.Boolean, default=True, nullable=False)

    # --- İlişkiler ---
    role = db.relationship("Role", back_populates="users")
    producer_profile = db.relationship(
        "ProducerProfile", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    cart = db.relationship(
        "Cart", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    orders = db.relationship("Order", back_populates="customer")
    reviews = db.relationship("Review", back_populates="customer")

    # --- Parola işlemleri (Hafta 5'te genişletilecek) ---
    def set_password(self, password):
        """Parolayı düz metin olarak değil, hash olarak saklar."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    # --- Rol kontrolleri ---
    def has_role(self, role_name):
        return self.role is not None and self.role.name == role_name

    @property
    def is_admin(self):
        return self.has_role(RoleName.ADMIN)

    @property
    def is_producer(self):
        return self.has_role(RoleName.PRODUCER)

    @property
    def is_customer(self):
        return self.has_role(RoleName.CUSTOMER)

    # Flask-Login, pasif hesapların giriş yapmasını bu özellik ile engeller
    @property
    def is_active(self):
        return self.is_active_account

    def __repr__(self):
        return f"<User {self.email}>"


@login_manager.user_loader
def load_user(user_id):
    """Flask-Login her istekte oturumdaki kullanıcıyı bu fonksiyonla bulur.

    Hafta 11: Menü her sayfada kullanıcının rolünü ve (üreticiyse) profilini kullanır.
    joinedload ile bunlar kullanıcıyla AYNI sorguda gelir: istek başına 3 yerine 1 sorgu.
    """
    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        return None  # Bozuk/değiştirilmiş oturum değeri
    return db.session.execute(
        db.select(User).options(joinedload(User.role), joinedload(User.producer_profile))
        .where(User.id == user_id)
    ).unique().scalar_one_or_none()
