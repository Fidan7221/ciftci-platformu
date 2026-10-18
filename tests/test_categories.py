"""Hafta 6 testleri: yönetici kategori yönetimi.

Çalıştırma: pytest -v tests/test_categories.py
"""
from app.extensions import db
from app.models import Category, Product
from app.services.auth_service import create_admin_user
from app.services.category_service import slugify
from tests.conftest import register_and_login


def login_admin(client):
    create_admin_user("Yönetici", "admin@test.com", "Yonetici123")
    client.post("/auth/login", data={"email": "admin@test.com", "password": "Yonetici123"})


def test_slugify_turkish_characters():
    assert slugify("Bal ve Arı Ürünleri") == "bal-ve-ari-urunleri"
    assert slugify("  Çiğ Süt & Peynir!  ") == "cig-sut-peynir"


def test_producer_cannot_manage_categories(client):
    register_and_login(client, "ciftci@test.com")
    assert client.get("/yonetici/kategoriler").status_code == 403
    assert client.post("/yonetici/kategoriler/yeni", data={"name": "Hack"}).status_code == 403


def test_admin_creates_subcategory_with_auto_slug(client):
    login_admin(client)
    sebze = Category.query.filter_by(slug="sebze").first()

    response = client.post("/yonetici/kategoriler/yeni",
                           data={"name": "Kırmızı Lahana", "slug": "", "parent_id": str(sebze.id)},
                           follow_redirects=True)
    assert "kategorisi eklendi" in response.get_data(as_text=True)

    lahana = Category.query.filter_by(slug="kirmizi-lahana").first()
    assert lahana is not None and lahana.parent == sebze


def test_duplicate_slug_rejected(client):
    login_admin(client)
    response = client.post("/yonetici/kategoriler/yeni",
                           data={"name": "Domates", "slug": "", "parent_id": "0"})
    assert "başka bir kategoride kullanılıyor" in response.get_data(as_text=True)


def test_three_levels_not_allowed(client):
    login_admin(client)
    domates = Category.query.filter_by(slug="domates").first()  # zaten bir alt kategori
    response = client.post("/yonetici/kategoriler/yeni",
                           data={"name": "Cherry", "slug": "", "parent_id": str(domates.id)})
    # domates üst kategori listesinde olmadığı için form "Not a valid choice" hatası verir
    assert response.status_code == 200
    assert Category.query.filter_by(slug="cherry").first() is None


def test_edit_category(client):
    login_admin(client)
    biber = Category.query.filter_by(slug="biber").first()
    client.post(f"/yonetici/kategoriler/{biber.id}/duzenle",
                data={"name": "Sivri Biber", "slug": "sivri-biber", "parent_id": str(biber.parent_id)})
    db.session.refresh(biber)
    assert biber.name == "Sivri Biber"


def test_cannot_delete_category_with_children(client):
    login_admin(client)
    sebze = Category.query.filter_by(slug="sebze").first()
    response = client.post(f"/yonetici/kategoriler/{sebze.id}/sil", follow_redirects=True)
    assert "alt kategorilerini" in response.get_data(as_text=True)
    assert Category.query.filter_by(slug="sebze").first() is not None


def test_cannot_delete_category_with_products(client, app):
    register_and_login(client, "ciftci@test.com")
    domates = Category.query.filter_by(slug="domates").first()
    client.post("/uretici/urunler/yeni", data={
        "name": "Domates", "category_id": str(domates.id), "unit": "kg", "stock_quantity": "10",
        "is_active": "y",
    }, content_type="multipart/form-data")
    assert Product.query.count() == 1
    client.post("/auth/logout")

    login_admin(client)
    response = client.post(f"/yonetici/kategoriler/{domates.id}/sil", follow_redirects=True)
    assert "ürünler var" in response.get_data(as_text=True)


def test_delete_empty_category(client):
    login_admin(client)
    patates = Category.query.filter_by(slug="patates").first()
    response = client.post(f"/yonetici/kategoriler/{patates.id}/sil", follow_redirects=True)
    assert "silindi" in response.get_data(as_text=True)
    assert Category.query.filter_by(slug="patates").first() is None
