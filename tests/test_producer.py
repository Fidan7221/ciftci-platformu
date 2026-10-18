"""Hafta 6 testleri: üretici profili ve ürün CRUD'u.

Çalıştırma: pytest -v tests/test_producer.py
"""
import io
import os
from decimal import Decimal

from app.extensions import db
from app.models import Category, Listing, Order, OrderItem, Product
from app.repositories.user_repository import UserRepository
from tests.conftest import register_and_login

# Geçerli PNG imzasıyla başlayan küçük sahte dosya
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def category_id(slug="domates"):
    return Category.query.filter_by(slug=slug).first().id


def product_data(**overrides):
    data = {
        "name": "Organik Domates",
        "category_id": str(category_id()),
        "unit": "kg",
        "stock_quantity": "120.5",
        "description": "Bingöl ovasından.",
        "is_organic": "y",
        "is_active": "y",
    }
    data.update(overrides)
    return data


def add_product(client, **overrides):
    return client.post("/uretici/urunler/yeni", data=product_data(**overrides),
                       content_type="multipart/form-data", follow_redirects=True)


def producer_of(email):
    return UserRepository.get_by_email(email).producer_profile


# --- Yetki ---------------------------------------------------------------

def test_customer_cannot_manage_products(client):
    register_and_login(client, "musteri@test.com", role="customer")
    assert client.get("/uretici/urunler").status_code == 403
    assert client.post("/uretici/urunler/yeni", data=product_data()).status_code == 403
    assert Product.query.count() == 0


def test_anonymous_redirected_from_products(client):
    response = client.get("/uretici/urunler/yeni")
    assert response.status_code == 302
    assert "/auth/login" in response.headers["Location"]


# --- Profil ---------------------------------------------------------------

def test_update_profile(client):
    register_and_login(client, "ciftci@test.com")
    response = client.post("/uretici/profil", data={
        "full_name": "Ali Çiftçi", "phone": "05321234567", "city": "Bingöl",
        "farm_name": "Yeni Çiftlik", "region": "Bingöl / Solhan",
        "tax_number": "", "description": "Organik bal üretiyoruz.",
    }, follow_redirects=True)

    assert "Profiliniz güncellendi" in response.get_data(as_text=True)
    profile = producer_of("ciftci@test.com")
    assert profile.farm_name == "Yeni Çiftlik"
    assert profile.user.phone == "05321234567"


def test_profile_requires_farm_name(client):
    register_and_login(client, "ciftci@test.com")
    response = client.post("/uretici/profil", data={
        "full_name": "Ali Çiftçi", "farm_name": "", "region": "Bingöl",
    })
    assert "Çiftlik adı zorunludur" in response.get_data(as_text=True)


# --- Ürün ekleme ------------------------------------------------------------

def test_create_product_without_image(client):
    register_and_login(client, "ciftci@test.com")
    response = add_product(client)

    assert "ürününüz eklendi" in response.get_data(as_text=True)
    product = Product.query.one()
    assert product.stock_quantity == Decimal("120.50")
    assert product.is_organic and product.is_active
    assert product.producer == producer_of("ciftci@test.com")


def test_create_product_with_image(client, app):
    register_and_login(client, "ciftci@test.com")
    add_product(client, image=(io.BytesIO(PNG_BYTES), "domates.png"))

    product = Product.query.one()
    assert product.image_path.startswith("products/")
    assert product.image_path != "products/domates.png"  # ad rastgele üretildi
    assert os.path.isfile(os.path.join(app.config["UPLOAD_FOLDER"], product.image_path))


def test_fake_image_rejected(client):
    register_and_login(client, "ciftci@test.com")
    response = add_product(client, image=(io.BytesIO(b"<?php system('ls'); ?>"), "kotu.png"))
    assert "geçerli bir resim değil" in response.get_data(as_text=True)
    assert Product.query.count() == 0


def test_wrong_extension_rejected(client):
    register_and_login(client, "ciftci@test.com")
    response = add_product(client, image=(io.BytesIO(b"MZ..."), "virus.exe"))
    assert "Yalnızca JPG, PNG veya WEBP" in response.get_data(as_text=True)
    assert Product.query.count() == 0


def test_negative_stock_rejected(client):
    register_and_login(client, "ciftci@test.com")
    response = add_product(client, stock_quantity="-3")
    assert "Stok negatif olamaz" in response.get_data(as_text=True)
    assert Product.query.count() == 0


def test_zero_stock_allowed(client):
    register_and_login(client, "ciftci@test.com")
    add_product(client, stock_quantity="0")
    assert Product.query.one().stock_quantity == 0


# --- Listeleme --------------------------------------------------------------

def test_list_shows_only_own_products(client):
    register_and_login(client, "ali@test.com", farm_name="Ali Çiftliği")
    add_product(client, name="Ali Domatesi")
    client.post("/auth/logout")

    register_and_login(client, "veli@test.com", farm_name="Veli Çiftliği")
    add_product(client, name="Veli Biberi", category_id=str(category_id("biber")))

    page = client.get("/uretici/urunler").get_data(as_text=True)
    assert "Veli Biberi" in page
    assert "Ali Domatesi" not in page


def test_search_and_category_filter(client):
    register_and_login(client, "ciftci@test.com")
    add_product(client, name="Salkım Domates")
    add_product(client, name="Çarliston Biber", category_id=str(category_id("biber")))

    page = client.get("/uretici/urunler?q=Salk").get_data(as_text=True)
    assert "Salkım Domates" in page and "Çarliston Biber" not in page

    page = client.get(f"/uretici/urunler?kategori={category_id('biber')}").get_data(as_text=True)
    assert "Çarliston Biber" in page and "Salkım Domates" not in page


# --- Güncelleme ---------------------------------------------------------------

def test_update_product(client):
    register_and_login(client, "ciftci@test.com")
    add_product(client)
    product = Product.query.one()

    client.post(f"/uretici/urunler/{product.id}/duzenle",
                data=product_data(name="Salkım Domates", stock_quantity="80", is_active=""),
                content_type="multipart/form-data")

    db.session.refresh(product)
    assert product.name == "Salkım Domates"
    assert product.stock_quantity == Decimal("80")
    assert product.is_active is False


def test_replacing_image_deletes_old_file(client, app):
    register_and_login(client, "ciftci@test.com")
    add_product(client, image=(io.BytesIO(PNG_BYTES), "eski.png"))
    product = Product.query.one()
    old_path = os.path.join(app.config["UPLOAD_FOLDER"], product.image_path)

    client.post(f"/uretici/urunler/{product.id}/duzenle",
                data=product_data(image=(io.BytesIO(PNG_BYTES), "yeni.png")),
                content_type="multipart/form-data")

    db.session.refresh(product)
    assert not os.path.exists(old_path)
    assert os.path.isfile(os.path.join(app.config["UPLOAD_FOLDER"], product.image_path))


def test_cannot_edit_other_producers_product(client):
    register_and_login(client, "ali@test.com", farm_name="Ali Çiftliği")
    add_product(client)
    product_id = Product.query.one().id
    client.post("/auth/logout")

    register_and_login(client, "veli@test.com", farm_name="Veli Çiftliği")
    assert client.get(f"/uretici/urunler/{product_id}/duzenle").status_code == 404
    response = client.post(f"/uretici/urunler/{product_id}/duzenle",
                           data=product_data(name="Çalındı"), content_type="multipart/form-data")
    assert response.status_code == 404
    assert client.post(f"/uretici/urunler/{product_id}/sil").status_code == 404
    assert Product.query.one().name == "Organik Domates"


# --- Silme ------------------------------------------------------------------

def test_delete_product_removes_row_and_image(client, app):
    register_and_login(client, "ciftci@test.com")
    add_product(client, image=(io.BytesIO(PNG_BYTES), "domates.png"))
    product = Product.query.one()
    image_file = os.path.join(app.config["UPLOAD_FOLDER"], product.image_path)

    response = client.post(f"/uretici/urunler/{product.id}/sil", follow_redirects=True)
    assert "silindi" in response.get_data(as_text=True)
    assert Product.query.count() == 0
    assert not os.path.exists(image_file)


def test_delete_requires_post(client):
    register_and_login(client, "ciftci@test.com")
    add_product(client)
    product_id = Product.query.one().id
    assert client.get(f"/uretici/urunler/{product_id}/sil").status_code == 405


def test_product_with_orders_is_archived_not_deleted(client):
    register_and_login(client, "ciftci@test.com")
    add_product(client)
    product = Product.query.one()

    # Ürünün bir ilanı ve o ilana ait bir sipariş olsun
    customer = UserRepository.get_by_email("ciftci@test.com")  # sipariş sahibinin kim olduğu önemsiz
    listing = Listing(product=product, title="Domates", price=Decimal("20"), stock_quantity=Decimal("10"))
    order = Order(customer=customer, total_amount=Decimal("40"), shipping_address="Bingöl",
                  items=[OrderItem(listing=listing, producer=product.producer,
                                   quantity=Decimal("2"), unit_price=Decimal("20"))])
    db.session.add_all([listing, order])
    db.session.commit()

    response = client.post(f"/uretici/urunler/{product.id}/sil", follow_redirects=True)
    assert "arşive alındı" in response.get_data(as_text=True)
    db.session.refresh(product)
    assert product.is_active is False
    assert OrderItem.query.count() == 1  # sipariş geçmişi korundu


# --- Panel --------------------------------------------------------------------

def test_dashboard_stats(client):
    register_and_login(client, "ciftci@test.com", farm_name="Genç Çiftliği")
    add_product(client, name="Az Stoklu", stock_quantity="2")
    add_product(client, name="Bol Stoklu", stock_quantity="500")

    page = client.get("/uretici/panel").get_data(as_text=True)
    assert "Genç Çiftliği" in page
    assert "Az Stoklu" in page and "Bol Stoklu" in page
