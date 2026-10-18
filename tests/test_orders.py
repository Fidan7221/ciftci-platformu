"""Hafta 7 testleri: sipariş oluşturma (transaction), fiyat dondurma ve durum yönetimi.

Çalıştırma: pytest -v tests/test_orders.py
"""
from decimal import Decimal

import pytest

from sqlalchemy import update

from app.extensions import db
from app.models import CartItem, Listing, ListingStatus, Order, OrderItem, OrderStatus, Product
from app.services import cart_service, order_service
from app.services.errors import ServiceError
from tests.conftest import login, make_customer, make_listing, make_producer, make_product

ADDRESS = "Yenişehir Mah. Çiçek Sok. No:5 Merkez / Bingöl"


def checkout(client, address=ADDRESS):
    return client.post("/sepet/onay", data={"shipping_address": address, "note": "", "save_address": "y"},
                       follow_redirects=True)


def prepare(quantity_in_cart="10", listing_qty="50", product_stock="100", price="20"):
    """Bir üretici, bir ilan ve sepetinde o ilandan ürün olan bir müşteri hazırlar."""
    profile = make_producer("ciftci@test.com", farm_name="Genç Çiftliği")
    product = make_product(profile, stock=product_stock)
    listing = make_listing(profile, product, quantity=listing_qty, price=price)
    customer = make_customer("musteri@test.com")
    cart_service.add_to_cart(customer, listing.id, Decimal(quantity_in_cart))
    return profile, product, listing, customer


def set_status(client, order_id, status):
    return client.post(f"/siparisler/{order_id}/durum", data={"status": status}, follow_redirects=True)


# --- Sipariş oluşturma -----------------------------------------------------------

def test_checkout_creates_order_and_decreases_both_stocks(client):
    _, product, listing, customer = prepare(quantity_in_cart="10")
    login(client, "musteri@test.com")

    assert "Siparişiniz alındı" in checkout(client).get_data(as_text=True)

    order = Order.query.one()
    assert order.status == OrderStatus.PENDING
    assert order.total_amount == Decimal("200.00")
    assert order.items[0].unit_price == Decimal("20.00")
    assert order.items[0].producer_id == product.producer_id

    db.session.refresh(listing)
    db.session.refresh(product)
    assert listing.stock_quantity == Decimal("40")   # 50 - 10
    assert product.stock_quantity == Decimal("90")   # 100 - 10
    assert CartItem.query.count() == 0                # sepet boşaldı
    assert customer.address == ADDRESS                # adres kaydedildi


def test_price_is_frozen_after_order(client):
    _, _, listing, _ = prepare(price="20")
    login(client, "musteri@test.com")
    checkout(client)

    listing.price = Decimal("35")  # üretici fiyatı sonradan artırdı
    db.session.commit()

    item = OrderItem.query.one()
    assert item.unit_price == Decimal("20.00")
    assert Order.query.one().total_amount == Decimal("200.00")


def test_cart_with_two_producers_is_split(client):
    ali = make_producer("ali@test.com", farm_name="Ali Çiftliği")
    veli = make_producer("veli@test.com", farm_name="Veli Bahçesi")
    l1 = make_listing(ali, make_product(ali), price="10")
    l2 = make_listing(veli, make_product(veli, slug="biber"), price="15")
    customer = make_customer("musteri@test.com")
    cart_service.add_to_cart(customer, l1.id, Decimal("2"))
    cart_service.add_to_cart(customer, l2.id, Decimal("4"))

    login(client, "musteri@test.com")
    assert "2 ayrı siparişe" in checkout(client).get_data(as_text=True)

    orders = Order.query.order_by(Order.total_amount).all()
    assert [o.total_amount for o in orders] == [Decimal("20.00"), Decimal("60.00")]
    assert {o.producer.farm_name for o in orders} == {"Ali Çiftliği", "Veli Bahçesi"}


def test_buying_all_stock_marks_listing_sold_out(client):
    _, _, listing, _ = prepare(quantity_in_cart="50", listing_qty="50")
    login(client, "musteri@test.com")
    checkout(client)
    db.session.refresh(listing)
    assert listing.stock_quantity == 0
    assert listing.status == ListingStatus.SOLD_OUT


def test_failure_rolls_back_everything(client):
    """İkinci kalem atomik stok kontrolünde başarısız olursa ilk kalemin stok düşümü de geri alınmalı."""
    profile = make_producer("ciftci@test.com")
    good_product = make_product(profile, name="Domates", stock="100")
    bad_product = make_product(profile, name="Biber", stock="100", slug="biber")
    good = make_listing(profile, good_product, quantity="50")
    bad = make_listing(profile, bad_product, quantity="50")
    customer = make_customer("musteri@test.com")
    cart_service.add_to_cart(customer, good.id, Decimal("10"))
    cart_service.add_to_cart(customer, bad.id, Decimal("10"))

    # Depodaki biber dışarıdan azaldı (ör. üretici elden sattı): ilan stoğu yeterli görünüyor ama depo değil
    db.session.execute(update(Product).where(Product.id == bad_product.id).values(stock_quantity=5))
    db.session.commit()

    with pytest.raises(ServiceError):
        order_service.place_order(customer, ADDRESS)

    db.session.refresh(good)
    db.session.refresh(good_product)
    assert Order.query.count() == 0 and OrderItem.query.count() == 0
    assert good.stock_quantity == Decimal("50")          # ilk kalemin düşümü geri alındı
    assert good_product.stock_quantity == Decimal("100")
    assert CartItem.query.count() == 2                    # sepet olduğu gibi duruyor


def test_stock_taken_by_someone_else_is_caught(client):
    _, _, listing, customer = prepare(quantity_in_cart="30", listing_qty="50")
    other = make_customer("diger@test.com")
    cart_service.add_to_cart(other, listing.id, Decimal("30"))

    order_service.place_order(other, ADDRESS)  # diğer müşteri önce tamamladı: 20 kaldı

    with pytest.raises(ServiceError):
        order_service.place_order(customer, ADDRESS)
    assert Order.query.count() == 1
    db.session.refresh(listing)
    assert listing.stock_quantity == Decimal("20")


def test_empty_cart_and_short_address(client):
    make_customer("musteri@test.com")
    login(client, "musteri@test.com")
    response = client.get("/sepet/onay")
    assert response.status_code == 302  # boş sepet -> pazara yönlendirir

    producer = make_producer("ciftci@test.com")
    listing = make_listing(producer, make_product(producer))
    client.post(f"/sepet/ekle/{listing.id}", data={"quantity": "1"})
    page = checkout(client, address="kısa").get_data(as_text=True)
    assert "10-255 karakter" in page
    assert Order.query.count() == 0


# --- Durum yönetimi ---------------------------------------------------------------

def test_full_lifecycle(client):
    prepare()
    login(client, "musteri@test.com")
    checkout(client)
    order = Order.query.one()

    login(client, "ciftci@test.com")
    set_status(client, order.id, OrderStatus.PAID)
    set_status(client, order.id, OrderStatus.SHIPPED)
    db.session.refresh(order)
    assert order.status == OrderStatus.SHIPPED

    login(client, "musteri@test.com")
    response = set_status(client, order.id, OrderStatus.DELIVERED)
    assert "Teslim edildi" in response.get_data(as_text=True)
    db.session.refresh(order)
    assert order.status == OrderStatus.DELIVERED


def test_invalid_transitions_rejected(client):
    _, _, _, customer = prepare()
    order = order_service.place_order(customer, ADDRESS)[0]

    login(client, "musteri@test.com")
    page = set_status(client, order.id, OrderStatus.PAID).get_data(as_text=True)  # müşteri ödeme onaylayamaz
    assert "geçirilemez" in page

    login(client, "ciftci@test.com")
    set_status(client, order.id, OrderStatus.SHIPPED)   # ödenmeden kargolanamaz
    set_status(client, order.id, OrderStatus.DELIVERED)  # teslimi üretici onaylayamaz
    db.session.refresh(order)
    assert order.status == OrderStatus.PENDING


def test_cancel_restores_stock_and_reopens_listing(client):
    _, product, listing, customer = prepare(quantity_in_cart="50", listing_qty="50")
    order = order_service.place_order(customer, ADDRESS)[0]
    db.session.refresh(listing)
    assert listing.status == ListingStatus.SOLD_OUT

    login(client, "musteri@test.com")
    set_status(client, order.id, OrderStatus.CANCELLED)

    db.session.refresh(order)
    db.session.refresh(listing)
    db.session.refresh(product)
    assert order.status == OrderStatus.CANCELLED
    assert listing.stock_quantity == Decimal("50") and listing.status == ListingStatus.ACTIVE
    assert product.stock_quantity == Decimal("100")


def test_customer_cannot_cancel_after_payment_and_no_double_cancel(client):
    _, product, _, customer = prepare(quantity_in_cart="10")
    order = order_service.place_order(customer, ADDRESS)[0]

    login(client, "ciftci@test.com")
    set_status(client, order.id, OrderStatus.PAID)

    login(client, "musteri@test.com")
    set_status(client, order.id, OrderStatus.CANCELLED)
    db.session.refresh(order)
    assert order.status == OrderStatus.PAID  # ödendikten sonra müşteri iptal edemez

    login(client, "ciftci@test.com")
    set_status(client, order.id, OrderStatus.CANCELLED)  # üretici iptal edebilir
    set_status(client, order.id, OrderStatus.CANCELLED)  # ikinci iptal reddedilir
    db.session.refresh(product)
    assert product.stock_quantity == Decimal("100")       # stok yalnızca BİR kez geri eklendi


def test_order_visibility(client):
    _, _, _, customer = prepare()
    order = order_service.place_order(customer, ADDRESS)[0]
    make_customer("yabanci@test.com")
    make_producer("baska@test.com", farm_name="Başka Çiftlik")

    login(client, "musteri@test.com")
    assert client.get(f"/siparisler/{order.id}").status_code == 200
    login(client, "ciftci@test.com")
    page = client.get(f"/siparisler/{order.id}").get_data(as_text=True)
    assert ADDRESS.split()[0] in page  # üretici teslimat adresini görür
    assert f"#{order.id}" in client.get("/uretici/siparisler").get_data(as_text=True)

    login(client, "yabanci@test.com")
    assert client.get(f"/siparisler/{order.id}").status_code == 404
    login(client, "baska@test.com")
    assert client.get(f"/siparisler/{order.id}").status_code == 404
    assert set_status(client, order.id, OrderStatus.PAID).status_code == 404
