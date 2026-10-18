"""Hafta 4 duman testi: tablolar oluşuyor ve ilişkiler çalışıyor mu?

Çalıştırma: pytest -v
"""
from decimal import Decimal

import pytest

from app import create_app
from app.extensions import db
from app.models import (
    Cart, CartItem, Category, Listing, Order, OrderItem,
    ProducerProfile, Product, Review, Role, RoleName, User,
)
from scripts.seed_data import seed_all


@pytest.fixture
def app():
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        seed_all()
        yield app
        db.session.remove()
        db.drop_all()


def make_user(email, role_name):
    role = Role.query.filter_by(name=role_name).first()
    user = User(full_name="Test", email=email, role=role)
    user.set_password("Gizli123!")
    db.session.add(user)
    return user


def test_seed_roles_and_categories(app):
    assert Role.query.count() == 3
    sebze = Category.query.filter_by(slug="sebze").first()
    assert {c.slug for c in sebze.children} >= {"domates", "biber"}


def test_password_is_hashed(app):
    user = make_user("a@test.com", RoleName.CUSTOMER)
    assert user.password_hash != "Gizli123!"
    assert user.check_password("Gizli123!")
    assert not user.check_password("yanlis")


def test_full_flow_relationships(app):
    # Üretici, ürün ve ilan
    farmer = make_user("ciftci@test.com", RoleName.PRODUCER)
    profile = ProducerProfile(user=farmer, farm_name="Genç Çiftliği", region="Bingöl / Genç")
    domates = Category.query.filter_by(slug="domates").first()
    product = Product(producer=profile, category=domates, name="Organik Domates")
    listing = Listing(product=product, title="Taze domates", price=Decimal("25.50"),
                      stock_quantity=Decimal("100"))

    # Müşteri sepeti
    customer = make_user("musteri@test.com", RoleName.CUSTOMER)
    cart = Cart(user=customer, items=[CartItem(listing=listing, quantity=Decimal("2"))])
    db.session.add_all([profile, product, listing, cart])
    db.session.commit()

    assert farmer.is_producer and customer.is_customer
    assert customer.cart.total == Decimal("51.00")

    # Sipariş ve değerlendirme
    item = OrderItem(listing=listing, producer=profile, quantity=Decimal("2"),
                     unit_price=listing.price)
    order = Order(customer=customer, total_amount=Decimal("51.00"),
                  shipping_address="Bingöl", items=[item])
    db.session.add(order)
    db.session.commit()

    review = Review(order_item=item, customer=customer, producer=profile, rating=5)
    db.session.add(review)
    db.session.commit()

    assert profile.order_items[0].order.customer.email == "musteri@test.com"
    assert profile.reviews[0].rating == 5
