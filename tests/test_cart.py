"""Hafta 7 testleri: sepet akışı.

Çalıştırma: pytest -v tests/test_cart.py
"""
from decimal import Decimal

from app.extensions import db
from app.models import CartItem
from app.services import listing_service
from tests.conftest import login, make_customer, make_listing, make_producer, make_product


def setup_listing(quantity="50", unit="kg", min_order="1", price="20"):
    profile = make_producer("ciftci@test.com")
    product = make_product(profile, unit=unit, stock="100")
    return profile, make_listing(profile, product, quantity=quantity, price=price, min_order=min_order)


def add(client, listing_id, quantity):
    return client.post(f"/sepet/ekle/{listing_id}", data={"quantity": quantity}, follow_redirects=True)


def test_add_to_cart_and_accumulate(client):
    _, listing = setup_listing()
    customer = make_customer("musteri@test.com")
    login(client, "musteri@test.com")

    assert "sepetinize eklendi" in add(client, listing.id, "3").get_data(as_text=True)
    add(client, listing.id, "2.5")

    item = CartItem.query.one()
    assert item.quantity == Decimal("5.5")
    assert customer.cart.total == Decimal("110")


def test_cannot_exceed_listing_stock(client):
    _, listing = setup_listing(quantity="10")
    make_customer("musteri@test.com")
    login(client, "musteri@test.com")

    assert "yalnızca 10 kg" in add(client, listing.id, "11").get_data(as_text=True)
    add(client, listing.id, "8")
    assert "yalnızca 10 kg" in add(client, listing.id, "3").get_data(as_text=True)  # 8 + 3 > 10
    assert CartItem.query.one().quantity == Decimal("8")


def test_min_order_enforced(client):
    _, listing = setup_listing(min_order="5")
    make_customer("musteri@test.com")
    login(client, "musteri@test.com")
    assert "en az 5 kg" in add(client, listing.id, "2").get_data(as_text=True)
    assert CartItem.query.count() == 0


def test_countable_unit_requires_whole_number(client):
    _, listing = setup_listing(unit="kasa")
    make_customer("musteri@test.com")
    login(client, "musteri@test.com")
    assert "tam sayı" in add(client, listing.id, "1.5").get_data(as_text=True)
    add(client, listing.id, "2")
    assert CartItem.query.one().quantity == Decimal("2")


def test_update_and_remove_item(client):
    _, listing = setup_listing()
    make_customer("musteri@test.com")
    login(client, "musteri@test.com")
    add(client, listing.id, "3")
    item = CartItem.query.one()

    client.post(f"/sepet/kalem/{item.id}", data={"quantity": "7"})
    db.session.refresh(item)
    assert item.quantity == Decimal("7")

    response = client.post(f"/sepet/kalem/{item.id}", data={"quantity": "0"}, follow_redirects=True)
    assert "sepetten çıkarıldı" in response.get_data(as_text=True)
    assert CartItem.query.count() == 0


def test_remove_item_route(client):
    _, listing = setup_listing()
    make_customer("musteri@test.com")
    login(client, "musteri@test.com")
    add(client, listing.id, "3")
    item_id = CartItem.query.one().id

    client.post(f"/sepet/kalem/{item_id}/sil")
    assert CartItem.query.count() == 0


def test_cannot_touch_other_customers_cart_item(client):
    _, listing = setup_listing()
    make_customer("ayse@test.com")
    make_customer("fatma@test.com")
    login(client, "ayse@test.com")
    add(client, listing.id, "3")
    item_id = CartItem.query.one().id

    login(client, "fatma@test.com")
    response = client.post(f"/sepet/kalem/{item_id}/sil", follow_redirects=True)
    assert "bulunamadı" in response.get_data(as_text=True)
    assert CartItem.query.count() == 1


def test_producer_cannot_use_cart(client):
    _, listing = setup_listing()
    login(client, "ciftci@test.com")
    assert client.post(f"/sepet/ekle/{listing.id}", data={"quantity": "1"}).status_code == 403
    assert client.get("/sepet/").status_code == 403


def test_closed_listing_cannot_be_added(client):
    profile, listing = setup_listing()
    listing_service.toggle_listing(profile, listing)
    make_customer("musteri@test.com")
    login(client, "musteri@test.com")
    assert "satışta değil" in add(client, listing.id, "1").get_data(as_text=True)


def test_cart_flags_listing_closed_after_adding(client):
    profile, listing = setup_listing()
    make_customer("musteri@test.com")
    login(client, "musteri@test.com")
    add(client, listing.id, "3")

    listing_service.toggle_listing(profile, listing)  # üretici satışı durdurdu

    page = client.get("/sepet/").get_data(as_text=True)
    assert "satışta değil" in page
    response = client.get("/sepet/onay")
    assert response.status_code == 302 and "/sepet/" in response.headers["Location"]


def test_cart_badge_count(client):
    _, listing = setup_listing()
    make_customer("musteri@test.com")
    login(client, "musteri@test.com")
    add(client, listing.id, "1")
    page = client.get("/pazar/").get_data(as_text=True)
    assert "Sepetim" in page
