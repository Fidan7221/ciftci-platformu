"""Tüm testlerin ortak hazırlıkları (pytest bu dosyayı otomatik bulur)."""
import pytest

from app import create_app
from app.extensions import db
from scripts.seed_data import seed_all


@pytest.fixture
def app(tmp_path):
    app = create_app("testing")
    # Testte yüklenen görseller gerçek static/uploads klasörünü kirletmesin
    app.config["UPLOAD_FOLDER"] = str(tmp_path / "uploads")
    with app.app_context():
        db.create_all()
        seed_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


# --- Ortak yardımcılar (Hafta 6) ------------------------------------------

def register_and_login(client, email, role="producer", farm_name="Test Çiftliği"):
    data = {
        "role": role,
        "full_name": "Test Kullanıcı",
        "email": email,
        "password": "Parola123",
        "confirm_password": "Parola123",
        "accept_terms": "y",
    }
    if role == "producer":
        data.update(farm_name=farm_name, region="Bingöl / Merkez")
    client.post("/auth/register", data=data)
    client.post("/auth/login", data={"email": email, "password": "Parola123"})


# --- Hafta 7 yardımcıları: verileri servisler üzerinden hızlıca hazırlar ------------

def login(client, email, password="Parola123"):
    client.post("/auth/logout")
    client.post("/auth/login", data={"email": email, "password": password})


def make_producer(email, farm_name="Test Çiftliği"):
    from app.services import auth_service
    user = auth_service.register_user("Üretici", email, "Parola123", "producer",
                                      farm_name=farm_name, region="Bingöl / Merkez")
    return user.producer_profile


def make_customer(email):
    from app.services import auth_service
    return auth_service.register_user("Müşteri", email, "Parola123", "customer")


def make_product(profile, name="Domates", stock="100", unit="kg", slug="domates"):
    from decimal import Decimal
    from app.models import Category
    from app.services import producer_service
    category = Category.query.filter_by(slug=slug).first()
    return producer_service.create_product(profile, category.id, name, unit, Decimal(stock))


def make_listing(profile, product, quantity="50", price="20", min_order="1", title=None):
    from datetime import date
    from decimal import Decimal
    from app.services import listing_service
    return listing_service.create_listing(profile, product.id, title, Decimal(price), Decimal(quantity),
                                          Decimal(min_order), date.today())
