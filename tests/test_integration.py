"""Hafta 8 (VİZE) entegrasyon testleri: modüllerin birbirine bağlı çalıştığını uçtan uca doğrular.

Birim testlerinden farkı: burada veriler servislerle değil, tamamen bir kullanıcının
yapacağı gibi HTTP istekleriyle (form gönderimi, sayfa gezintisi) oluşturulur.

Çalıştırma: pytest -v tests/test_integration.py
"""
import io
from datetime import date, datetime
from decimal import Decimal

from app.extensions import db
from app.models import Category, Listing, Order, OrderItem, OrderStatus, Product, User
from scripts.demo_data import DEMO_PASSWORD

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
ADDRESS = "Yenişehir Mah. Çiçek Sok. No:5 D:3 Merkez / Bingöl"


# --- Yardımcılar: hepsi gerçek HTTP istekleri --------------------------------------

def logout(client):
    client.post("/auth/logout")


def register(client, email, role, **extra):
    data = {"role": role, "full_name": "Test Kişi", "email": email, "password": "Parola123",
            "confirm_password": "Parola123", "accept_terms": "y", **extra}
    return client.post("/auth/register", data=data, follow_redirects=True)


def login(client, email, password="Parola123"):
    logout(client)
    return client.post("/auth/login", data={"email": email, "password": password}, follow_redirects=True)


def text(response):
    return response.get_data(as_text=True)


# --- 1. Uçtan uca pazar yeri senaryosu ------------------------------------------------

def test_full_marketplace_journey(client):
    # 1) Üretici kaydolur, giriş yapar ve profilini tamamlar
    page = text(register(client, "ciftci@test.com", "producer",
                         farm_name="Genç Çiftliği", region="Bingöl / Genç"))
    assert "Kaydınız oluşturuldu" in page
    assert "Üretici Paneli" in text(login(client, "ciftci@test.com"))

    page = text(client.post("/uretici/profil", data={
        "full_name": "Mehmet Yılmaz", "phone": "05321112233", "city": "Bingöl",
        "farm_name": "Genç Organik Çiftliği", "region": "Bingöl / Genç",
        "description": "İlaçsız tarım.", "tax_number": "",
    }, follow_redirects=True))
    assert "Profiliniz güncellendi" in page

    # 2) Görselli ürün ekler
    domates = Category.query.filter_by(slug="domates").first()
    page = text(client.post("/uretici/urunler/yeni", data={
        "name": "Salkım Domates", "category_id": str(domates.id), "unit": "kg",
        "stock_quantity": "100", "is_organic": "y", "is_active": "y",
        "image": (io.BytesIO(PNG_BYTES), "domates.png"),
    }, content_type="multipart/form-data", follow_redirects=True))
    assert "ürününüz eklendi" in page
    product = Product.query.one()

    # 3) Ürün kartındaki "İlan aç" bağlantısıyla ilan açar
    assert f"/uretici/ilanlar/yeni?urun={product.id}" in text(client.get("/uretici/urunler"))
    page = text(client.post("/uretici/ilanlar/yeni", data={
        "product_id": str(product.id), "title": "Taze Salkım Domates", "price": "28.50",
        "stock_quantity": "40", "min_order_quantity": "1",
        "start_date": date.today().isoformat(), "end_date": "", "is_active": "y",
    }, follow_redirects=True))
    assert "ilanı yayında" in page
    listing = Listing.query.one()

    # 4) Müşteri kaydolur; ilanı pazarda bulur ve detayını açar
    logout(client)
    register(client, "musteri@test.com", "customer")
    login(client, "musteri@test.com")
    market = text(client.get("/pazar/?q=Domates"))
    assert "Taze Salkım Domates" in market and "Genç Organik Çiftliği" in market
    assert "Sepete ekle" in text(client.get(f"/pazar/ilan/{listing.id}"))

    # 5) Sepete ekler, sepeti görür ve siparişi onaylar
    page = text(client.post(f"/sepet/ekle/{listing.id}", data={"quantity": "3"}, follow_redirects=True))
    assert "sepetinize eklendi" in page and "85,50 ₺" in page  # 3 x 28,50
    page = text(client.post("/sepet/onay", data={"shipping_address": ADDRESS, "note": "Hafta sonu",
                                                 "save_address": "y"}, follow_redirects=True))
    assert "Siparişiniz alındı" in page
    order = Order.query.one()
    assert order.total_amount == Decimal("85.50") and order.status == OrderStatus.PENDING
    assert f"#{order.id}" in text(client.get("/siparisler/"))
    assert f"#{order.id}" in text(client.get("/musteri/panel"))

    # 6) Üretici siparişi panelinde görür, ödemeyi onaylar ve kargolar
    login(client, "ciftci@test.com")
    assert "İlgilenilecek sipariş" in text(client.get("/uretici/panel"))
    assert f"#{order.id}" in text(client.get("/uretici/siparisler"))
    client.post(f"/siparisler/{order.id}/durum", data={"status": OrderStatus.PAID})
    client.post(f"/siparisler/{order.id}/durum", data={"status": OrderStatus.SHIPPED})

    # 7) Müşteri teslim aldığını onaylar
    login(client, "musteri@test.com")
    page = text(client.post(f"/siparisler/{order.id}/durum", data={"status": OrderStatus.DELIVERED},
                            follow_redirects=True))
    assert "Teslim edildi" in page

    # 8) Tüm modüllerin ortak sonucu: stoklar, dondurulmuş fiyat, kayıtlı adres
    db.session.refresh(listing)
    db.session.refresh(product)
    db.session.refresh(order)
    assert order.status == OrderStatus.DELIVERED
    assert listing.stock_quantity == Decimal("37") and product.stock_quantity == Decimal("97")
    assert OrderItem.query.one().unit_price == Decimal("28.50")
    assert User.query.filter_by(email="musteri@test.com").one().address == ADDRESS


# --- 2. Her rol için tüm sayfalar açılıyor mu? (kırık bağlantı / şablon hatası taraması) ---

def seed_demo(app):
    result = app.test_cli_runner().invoke(args=["seed-demo"])
    assert result.exit_code == 0, result.output
    return result


def test_every_page_opens_for_each_role(client, app):
    seed_demo(app)
    product = Product.query.filter_by(name="Salkım Domates").one()
    listing = Listing.query.filter_by(product_id=product.id).first()

    public = ["/", "/pazar/", f"/pazar/ilan/{listing.id}", "/auth/login", "/auth/register"]
    pages = {
        "ciftci@demo.com": ["/panel", "/uretici/panel", "/uretici/profil", "/uretici/urunler",
                            "/uretici/urunler/yeni", f"/uretici/urunler/{product.id}/duzenle",
                            "/uretici/ilanlar", "/uretici/ilanlar/yeni",
                            f"/uretici/ilanlar/{listing.id}/duzenle", "/uretici/siparisler", "/hesabim"],
        "musteri@demo.com": ["/panel", "/musteri/panel", "/sepet/", "/siparisler/", "/hesabim"],
        "admin@demo.com": ["/panel", "/yonetici/panel", "/yonetici/kategoriler",
                           "/yonetici/kategoriler/yeni", "/yonetici/siparisler", "/hesabim"],
    }

    for url in public:
        assert client.get(url).status_code == 200, url

    for email, urls in pages.items():
        login(client, email, DEMO_PASSWORD)
        for url in urls + public[:3]:
            response = client.get(url, follow_redirects=True)
            assert response.status_code == 200, f"{email} -> {url}: {response.status_code}"


def test_protected_pages_redirect_anonymous_to_login(client):
    for url in ["/panel", "/uretici/urunler", "/sepet/", "/siparisler/", "/yonetici/panel", "/hesabim"]:
        response = client.get(url)
        assert response.status_code == 302 and "/auth/login" in response.headers["Location"], url


def test_navbar_matches_role(client, app):
    seed_demo(app)

    login(client, "ciftci@demo.com", DEMO_PASSWORD)
    page = text(client.get("/pazar/"))
    assert all(link in page for link in ("İlanlarım", "Gelen Siparişler", "Üretici profilim"))
    assert "Sepetim" not in page

    login(client, "musteri@demo.com", DEMO_PASSWORD)
    page = text(client.get("/pazar/"))
    assert all(link in page for link in ("Sepetim", "Siparişlerim", "Hesap bilgilerim"))
    assert "İlanlarım" not in page

    login(client, "admin@demo.com", DEMO_PASSWORD)
    page = text(client.get("/pazar/"))
    assert "Kategoriler" in page and "Sepetim" not in page

    logout(client)
    page = text(client.get("/pazar/"))
    assert "Giriş Yap" in page and "Kayıt Ol" in page


def test_active_menu_item_is_marked(client, app):
    seed_demo(app)
    login(client, "ciftci@demo.com", DEMO_PASSWORD)
    page = text(client.get("/uretici/ilanlar"))
    assert 'aria-current="page"' in page


# --- 3. Demo verisi ve hesap sayfası ------------------------------------------------------

def test_seed_demo_is_repeatable_and_usable(client, app):
    first = seed_demo(app)
    assert "musteri@demo.com" in first.output
    counts = (User.query.count(), Product.query.count(), Listing.query.count())
    seed_demo(app)  # ikinci çalıştırma kopya oluşturmamalı
    assert (User.query.count(), Product.query.count(), Listing.query.count()) == counts

    assert "Salkım Domates" in text(client.get("/pazar/"))
    assert "Müşteri Paneli" in text(login(client, "musteri@demo.com", DEMO_PASSWORD))


def test_account_address_is_used_at_checkout(client, app):
    seed_demo(app)
    login(client, "musteri@demo.com", DEMO_PASSWORD)
    new_address = "Saray Mah. Hükümet Cad. No:10 Merkez / Bingöl"
    page = text(client.post("/hesabim", data={"full_name": "Zeynep Kaya", "phone": "05357778899",
                                              "city": "Bingöl", "address": new_address},
                            follow_redirects=True))
    assert "Hesap bilgileriniz güncellendi" in page

    listing = Listing.query.first()
    client.post(f"/sepet/ekle/{listing.id}", data={"quantity": str(listing.min_order_quantity)})
    assert new_address in text(client.get("/sepet/onay"))  # adres formda hazır gelir


def test_producer_account_link_goes_to_producer_profile(client, app):
    seed_demo(app)
    login(client, "ciftci@demo.com", DEMO_PASSWORD)
    response = client.get("/hesabim")
    assert response.status_code == 302 and "/uretici/profil" in response.headers["Location"]


# --- 4. Hata yönetimi ve güvenlik ayarları --------------------------------------------------

def test_csrf_is_enforced_when_enabled(client, app):
    app.config["WTF_CSRF_ENABLED"] = True  # Testlerde kapalı; burada gerçek ortamdaki gibi açıyoruz
    assert 'name="csrf_token"' in text(client.get("/auth/login"))

    response = client.post("/auth/login", data={"email": "x@test.com", "password": "Parola123"},
                           headers={"Referer": "http://localhost/auth/login"}, follow_redirects=True)
    assert "Güvenlik anahtarının süresi doldu" in text(response)


def test_csrf_error_does_not_redirect_to_other_sites(client, app):
    app.config["WTF_CSRF_ENABLED"] = True
    response = client.post("/auth/login", data={}, headers={"Referer": "https://kotu-site.com/"})
    assert response.status_code == 302 and "kotu-site.com" not in response.headers["Location"]


def test_server_error_page_and_rollback(client, app):
    app.config["PROPAGATE_EXCEPTIONS"] = False  # Testte hatanın 500 sayfasına dönüşmesini görmek için

    @app.route("/_test_hata")
    def broken():
        raise RuntimeError("deneme hatası")

    response = client.get("/_test_hata")
    assert response.status_code == 500
    assert "Beklenmeyen bir hata" in text(response)


def test_404_page(client):
    response = client.get("/olmayan-sayfa")
    assert response.status_code == 404 and "Sayfa bulunamadı" in text(response)


def test_times_are_shown_in_turkey_time(app):
    to_text = app.jinja_env.filters["datetime_tr"]
    assert to_text(datetime(2026, 10, 18, 21, 30)) == "19.10.2026 00:30"  # UTC 21:30 -> TR 00:30


def test_version_is_shown_in_footer(client, app):
    assert f"v{app.config['APP_VERSION']}" in text(client.get("/"))
