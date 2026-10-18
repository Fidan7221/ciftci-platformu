"""Hafta 7 testleri: ilan yönetimi ve pazar vitrini.

Çalıştırma: pytest -v tests/test_listings.py
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.extensions import db
from app.models import Listing, ListingStatus
from app.services import listing_service, producer_service
from app.services.errors import ServiceError
from tests.conftest import login, make_customer, make_listing, make_producer, make_product


def listing_form(product_id, **overrides):
    data = {
        "product_id": str(product_id),
        "title": "Taze domates",
        "price": "25.50",
        "stock_quantity": "40",
        "min_order_quantity": "1",
        "start_date": date.today().isoformat(),
        "end_date": "",
        "is_active": "y",
    }
    data.update(overrides)
    return data


# --- Oluşturma ---------------------------------------------------------------

def test_producer_creates_listing_and_it_appears_in_market(client):
    profile = make_producer("ciftci@test.com", farm_name="Genç Çiftliği")
    product = make_product(profile, stock="100")
    login(client, "ciftci@test.com")

    response = client.post("/uretici/ilanlar/yeni", data=listing_form(product.id), follow_redirects=True)
    assert "ilanı yayında" in response.get_data(as_text=True)

    listing = Listing.query.one()
    assert listing.price == Decimal("25.50") and listing.status == ListingStatus.ACTIVE

    page = client.get("/pazar/").get_data(as_text=True)
    assert "Taze domates" in page and "Genç Çiftliği" in page


def test_empty_title_uses_product_name(client):
    profile = make_producer("ciftci@test.com")
    product = make_product(profile, name="Salkım Domates")
    listing = make_listing(profile, product, title="")
    assert listing.title == "Salkım Domates"


def test_listing_cannot_exceed_product_stock(client):
    profile = make_producer("ciftci@test.com")
    product = make_product(profile, stock="30")
    login(client, "ciftci@test.com")

    response = client.post("/uretici/ilanlar/yeni", data=listing_form(product.id, stock_quantity="31"))
    assert "en fazla 30 kg" in response.get_data(as_text=True)
    assert Listing.query.count() == 0


def test_active_listings_share_product_stock(client):
    profile = make_producer("ciftci@test.com")
    product = make_product(profile, stock="100")
    first = make_listing(profile, product, quantity="70")

    with pytest.raises(ServiceError):
        make_listing(profile, product, quantity="40")  # 70 + 40 > 100

    listing_service.toggle_listing(profile, first)  # ilk ilanı pasif yap -> stok serbest kalır
    second = make_listing(profile, product, quantity="40")
    assert second.status == ListingStatus.ACTIVE

    with pytest.raises(ServiceError):
        listing_service.toggle_listing(profile, first)  # tekrar açılırsa 70 + 40 > 100


def test_product_stock_cannot_drop_below_active_listings(client):
    profile = make_producer("ciftci@test.com")
    product = make_product(profile, stock="100")
    make_listing(profile, product, quantity="60")

    with pytest.raises(ServiceError) as error:
        producer_service.update_product(product, product.category_id, product.name, "kg", Decimal("50"))
    assert "ayrılmış" in error.value.message


def test_min_order_and_dates_validated(client):
    profile = make_producer("ciftci@test.com")
    product = make_product(profile)
    login(client, "ciftci@test.com")

    page = client.post("/uretici/ilanlar/yeni",
                       data=listing_form(product.id, stock_quantity="5", min_order_quantity="10")).get_data(as_text=True)
    assert "Minimum sipariş" in page

    yesterday = (date.today() - timedelta(days=1)).isoformat()
    page = client.post("/uretici/ilanlar/yeni",
                       data=listing_form(product.id, end_date=yesterday)).get_data(as_text=True)
    assert "Bitiş tarihi başlangıç" in page
    assert Listing.query.count() == 0


def test_price_must_be_positive(client):
    profile = make_producer("ciftci@test.com")
    product = make_product(profile)
    login(client, "ciftci@test.com")
    page = client.post("/uretici/ilanlar/yeni", data=listing_form(product.id, price="0")).get_data(as_text=True)
    assert "Fiyat sıfırdan büyük" in page


# --- Güncelleme ve durum --------------------------------------------------------

def test_toggle_listing_via_route(client):
    profile = make_producer("ciftci@test.com")
    listing = make_listing(profile, make_product(profile))
    login(client, "ciftci@test.com")

    client.post(f"/uretici/ilanlar/{listing.id}/durum")
    db.session.refresh(listing)
    assert listing.status == ListingStatus.CLOSED

    client.post(f"/uretici/ilanlar/{listing.id}/durum")
    db.session.refresh(listing)
    assert listing.status == ListingStatus.ACTIVE


def test_edit_listing_price(client):
    profile = make_producer("ciftci@test.com")
    product = make_product(profile)
    listing = make_listing(profile, product, price="20")
    login(client, "ciftci@test.com")

    client.post(f"/uretici/ilanlar/{listing.id}/duzenle",
                data=listing_form(product.id, price="22.75", stock_quantity="50"))
    db.session.refresh(listing)
    assert listing.price == Decimal("22.75")


def test_other_producer_cannot_edit_listing(client):
    owner = make_producer("ali@test.com", farm_name="Ali Çiftliği")
    listing = make_listing(owner, make_product(owner))
    make_producer("veli@test.com", farm_name="Veli Çiftliği")
    login(client, "veli@test.com")

    assert client.get(f"/uretici/ilanlar/{listing.id}/duzenle").status_code == 404
    assert client.post(f"/uretici/ilanlar/{listing.id}/durum").status_code == 404


def test_customer_cannot_manage_listings(client):
    make_customer("musteri@test.com")
    login(client, "musteri@test.com")
    assert client.get("/uretici/ilanlar").status_code == 403
    assert client.get("/uretici/ilanlar/yeni").status_code == 403


# --- Pazar görünürlüğü ---------------------------------------------------------------

def test_market_hides_unavailable_listings(client):
    profile = make_producer("ciftci@test.com")
    visible = make_listing(profile, make_product(profile, name="Görünen Domates"), title="Görünen İlan")

    closed = make_listing(profile, make_product(profile, name="Kapalı"), title="Kapalı İlan")
    listing_service.toggle_listing(profile, closed)

    archived_product = make_product(profile, name="Arşiv")
    make_listing(profile, archived_product, title="Arşiv İlanı")
    archived_product.is_active = False

    future = make_listing(profile, make_product(profile, name="Gelecek"), title="Gelecek İlan")
    future.start_date = date.today() + timedelta(days=3)
    db.session.commit()

    page = client.get("/pazar/").get_data(as_text=True)
    assert "Görünen İlan" in page
    for hidden in ("Kapalı İlan", "Arşiv İlanı", "Gelecek İlan"):
        assert hidden not in page
    assert visible.is_available and not future.is_available


def test_market_search_by_farm_and_category(client):
    ali = make_producer("ali@test.com", farm_name="Ali Çiftliği")
    veli = make_producer("veli@test.com", farm_name="Veli Bahçesi")
    make_listing(ali, make_product(ali, name="Domates"), title="Ali Domatesi")
    make_listing(veli, make_product(veli, name="Biber", slug="biber"), title="Veli Biberi")

    page = client.get("/pazar/?q=Bahçe").get_data(as_text=True)
    assert "Veli Biberi" in page and "Ali Domatesi" not in page

    from app.models import Category
    sebze = Category.query.filter_by(slug="sebze").first()  # üst kategori: alt kategorileri de kapsar
    page = client.get(f"/pazar/?kategori={sebze.id}").get_data(as_text=True)
    assert "Veli Biberi" in page and "Ali Domatesi" in page


def test_listing_detail_page(client):
    profile = make_producer("ciftci@test.com")
    listing = make_listing(profile, make_product(profile), title="Detay İlanı")
    page = client.get(f"/pazar/ilan/{listing.id}").get_data(as_text=True)
    assert "Detay İlanı" in page and "giriş yapın" in page
    assert client.get("/pazar/ilan/9999").status_code == 404
