"""Hafta 11 testleri: güvenlik, ince yetkilendirme (IDOR), kaba kuvvet koruması ve performans.

Her test bir SALDIRI SENARYOSUDUR: saldırganın ne denediği ve uygulamanın nasıl engellediği.
Çalıştırma: pytest -v tests/test_security.py
"""
import io
import re
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import inspect

from app import create_app
from app.extensions import db, login_manager
from app.models import CartItem, Listing, ListingStatus, Order, OrderStatus, ProducerProfile, Product, User
from app.services import cart_service, order_service
from tests.conftest import login, make_customer, make_listing, make_producer, make_product

ADDRESS = "Yenişehir Mah. Çiçek Sok. No:5 Merkez / Bingöl"
TEMPLATES = Path(__file__).resolve().parents[1] / "app" / "templates"


def text(response):
    return response.get_data(as_text=True)


def two_producers():
    """Ali'nin ürünü, ilanı ve bir müşterinin Ali'den verdiği sipariş; Veli saldırgan üretici."""
    ali = make_producer("ali@test.com", farm_name="Ali Çiftliği")
    product = make_product(ali, name="Ali Domatesi")
    listing = make_listing(ali, product, quantity="50")
    make_producer("veli@test.com", farm_name="Veli Çiftliği")
    customer = make_customer("musteri@test.com")
    cart_service.add_to_cart(customer, listing.id, Decimal("2"))
    order = order_service.place_order(customer, ADDRESS)[0]
    return product, listing, order


# =====================================================================================
# 1. Güvenlik başlıkları ve CSP
# =====================================================================================

def test_security_headers_on_every_response(client):
    headers = client.get("/").headers
    csp = headers["Content-Security-Policy"]
    for directive in ("default-src 'self'", "object-src 'none'", "frame-ancestors 'none'",
                      "form-action 'self'", "base-uri 'self'"):
        assert directive in csp
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["Referrer-Policy"] == "strict-origin-when-cross-origin"


def test_inline_scripts_carry_the_request_nonce(client):
    profile = make_producer("ciftci@test.com")
    make_product(profile)
    login(client, "ciftci@test.com")
    response = client.get("/uretici/ilanlar/yeni")
    nonce = re.search(r"'nonce-([^']+)'", response.headers["Content-Security-Policy"]).group(1)

    inline = [tag for tag in re.findall(r"<script[^>]*>", text(response))
              if "src=" not in tag and "application/json" not in tag]
    assert inline, "sayfada satır içi betik bekleniyordu"
    assert all(f'nonce="{nonce}"' in tag for tag in inline)


def test_nonce_is_different_on_every_request(client):
    first = client.get("/").headers["Content-Security-Policy"]
    second = client.get("/").headers["Content-Security-Policy"]
    assert first != second


def test_templates_contain_no_inline_event_handlers():
    # onclick="..." gibi işleyiciler CSP tarafından engellenir; ayrıca XSS için kolay hedeftir
    pattern = re.compile(r"""<[^>]+\son[a-z]+\s*=\s*["']|javascript:""", re.IGNORECASE)
    offenders = [str(path.relative_to(TEMPLATES)) for path in TEMPLATES.rglob("*.html")
                 if pattern.search(path.read_text(encoding="utf-8"))]
    assert offenders == []


# =====================================================================================
# 2. XSS: kullanıcı girdisi sayfada KOD olarak değil METİN olarak görünmeli
# =====================================================================================

PAYLOAD = '<script>alert("xss")</script>'


def test_product_and_listing_names_are_escaped(client):
    profile = make_producer("ciftci@test.com", farm_name='<img src=x onerror=alert(1)>')
    listing = make_listing(profile, make_product(profile, name=PAYLOAD), title=PAYLOAD)

    for url in ("/pazar/", f"/pazar/ilan/{listing.id}"):
        page = text(client.get(url))
        assert PAYLOAD not in page and "<img src=x" not in page
        assert "&lt;script&gt;" in page

    login(client, "ciftci@test.com")
    page = text(client.get("/uretici/urunler"))
    assert PAYLOAD not in page and "&lt;script&gt;" in page


def test_reflected_search_text_is_escaped(client):
    page = text(client.get('/pazar/?q="><script>alert(1)</script>'))
    assert "<script>alert(1)</script>" not in page
    assert "&#34;&gt;&lt;script&gt;" in page or "&quot;&gt;&lt;script&gt;" in page


def test_flash_message_with_user_input_is_escaped(client):
    profile = make_producer("ciftci@test.com")
    login(client, "ciftci@test.com")
    from app.models import Category
    category = Category.query.filter_by(slug="domates").one()
    page = text(client.post("/uretici/urunler/yeni", data={
        "name": PAYLOAD, "category_id": str(category.id), "unit": "kg", "stock_quantity": "5", "is_active": "y",
    }, content_type="multipart/form-data", follow_redirects=True))
    assert "ürününüz eklendi" in page and PAYLOAD not in page
    assert profile.products[0].name == PAYLOAD  # veri olduğu gibi saklanır, yalnızca gösterirken kaçırılır


# =====================================================================================
# 3. SQL injection ve LIKE joker karakterleri
# =====================================================================================

def test_sql_injection_in_search_is_treated_as_text(client):
    profile = make_producer("ciftci@test.com")
    make_listing(profile, make_product(profile), title="Taze Domates")
    response = client.get("/pazar/?q=' OR '1'='1' --")
    assert response.status_code == 200
    assert "Taze Domates" not in text(response)          # her şeyi döndürmedi
    assert "Aramanıza uyan ilan bulunamadı" in text(response)


def test_sql_injection_in_login_fails(client):
    make_customer("musteri@test.com")
    page = text(client.post("/auth/login", data={"email": "musteri@test.com' OR '1'='1",
                                                 "password": "' OR '1'='1"}, follow_redirects=True))
    assert "Hoş geldiniz" not in page
    assert client.get("/musteri/panel").status_code == 302  # giriş yapılmadı


def test_like_wildcards_are_escaped(client):
    profile = make_producer("ciftci@test.com")
    make_product(profile, name="100% Organik Domates")
    make_product(profile, name="Salkım Domates")
    login(client, "ciftci@test.com")

    page = text(client.get("/uretici/urunler", query_string={"q": "%"}))  # % artık joker değil, gerçek karakter
    assert "100% Organik Domates" in page and "Salkım Domates" not in page
    page = text(client.get("/uretici/urunler", query_string={"q": "_"}))  # _ de tek-karakter jokeri değil
    assert "Aramanıza uyan ürün bulunamadı" in page


# =====================================================================================
# 4. CSRF: geçerli anahtarı olmayan durum değiştiren istekler reddedilir
# =====================================================================================

def test_state_changing_requests_without_csrf_token_are_rejected(client, app):
    product, listing, order = two_producers()
    login(client, "ali@test.com")
    app.config["WTF_CSRF_ENABLED"] = True                 # gerçek ortamdaki gibi

    client.post(f"/uretici/urunler/{product.id}/sil")
    client.post(f"/siparisler/{order.id}/durum", data={"status": OrderStatus.CANCELLED})
    client.post(f"/uretici/ilanlar/{listing.id}/durum")

    db.session.expire_all()
    assert db.session.get(Product, product.id).is_active is True   # silinmedi / arşivlenmedi
    assert db.session.get(Order, order.id).status == OrderStatus.PENDING
    assert db.session.get(Listing, listing.id).status == ListingStatus.ACTIVE


# =====================================================================================
# 5. İnce yetkilendirme (IDOR): başkasının nesnesine id ile erişim
# =====================================================================================

def test_producer_cannot_touch_another_producers_product(client):
    product, _, _ = two_producers()
    login(client, "veli@test.com")
    assert client.get(f"/uretici/urunler/{product.id}/duzenle").status_code == 404
    assert client.post(f"/uretici/urunler/{product.id}/duzenle", data={"name": "Ele geçirildi"},
                       content_type="multipart/form-data").status_code == 404
    assert client.post(f"/uretici/urunler/{product.id}/sil").status_code == 404
    db.session.expire_all()
    assert db.session.get(Product, product.id).name == "Ali Domatesi"


def test_producer_cannot_touch_another_producers_listing(client):
    _, listing, _ = two_producers()
    login(client, "veli@test.com")
    assert client.get(f"/uretici/ilanlar/{listing.id}/duzenle").status_code == 404
    assert client.post(f"/uretici/ilanlar/{listing.id}/durum").status_code == 404
    db.session.expire_all()
    assert db.session.get(Listing, listing.id).status == ListingStatus.ACTIVE


def test_producer_cannot_list_another_producers_product_in_own_listing(client):
    product, _, _ = two_producers()
    login(client, "veli@test.com")
    make_product(db.session.execute(db.select(ProducerProfile).filter_by(farm_name="Veli Çiftliği")).scalar_one())
    client.post("/uretici/ilanlar/yeni", data={
        "product_id": str(product.id), "price": "1", "stock_quantity": "10", "min_order_quantity": "1",
        "start_date": date.today().isoformat(), "is_active": "y",
    })
    assert Listing.query.filter_by(product_id=product.id).count() == 1  # yalnızca Ali'nin kendi ilanı


def test_producer_cannot_see_or_change_orders_without_their_items(client):
    _, _, order = two_producers()
    login(client, "veli@test.com")
    assert client.get(f"/siparisler/{order.id}").status_code == 404
    assert client.post(f"/siparisler/{order.id}/durum", data={"status": OrderStatus.CANCELLED}).status_code == 404
    assert f"#{order.id}" not in text(client.get("/uretici/siparisler"))


def test_customer_cannot_access_another_customers_order_payment_or_cart(client):
    _, listing, order = two_producers()
    make_customer("baska@test.com")
    owner = User.query.filter_by(email="musteri@test.com").one()
    cart_service.add_to_cart(owner, listing.id, Decimal("1"))
    item_id = CartItem.query.one().id

    login(client, "baska@test.com")
    assert client.get(f"/siparisler/{order.id}").status_code == 404
    assert client.get(f"/odeme/siparis/{order.id}").status_code == 404
    assert client.post(f"/odeme/siparis/{order.id}", data={"holder": "x", "card_number": "4111111111111111",
                                                         "expiry": "12/99", "cvc": "123"}).status_code == 404
    client.post(f"/sepet/kalem/{item_id}", data={"quantity": "40"})
    client.post(f"/sepet/kalem/{item_id}/sil")
    db.session.expire_all()
    assert db.session.get(CartItem, item_id).quantity == Decimal("1")


@pytest.mark.parametrize("email, url", [
    ("musteri@test.com", "/uretici/panel"),
    ("musteri@test.com", "/uretici/urunler/yeni"),
    ("musteri@test.com", "/yonetici/panel"),
    ("musteri@test.com", "/yonetici/siparisler"),
    ("ali@test.com", "/yonetici/kategoriler"),
    ("ali@test.com", "/sepet/"),
    ("ali@test.com", "/siparisler/"),
])
def test_role_violations_return_403(client, email, url):
    two_producers()
    login(client, email)
    assert client.get(url).status_code == 403


def test_object_level_violations_return_404_not_403(client):
    """Başkasının nesnesinde 403 demek 'bu id'de bir şey var' bilgisini sızdırır; 404 sızdırmaz."""
    product, _, _ = two_producers()
    login(client, "veli@test.com")
    existing = client.get(f"/uretici/urunler/{product.id}/duzenle").status_code
    missing = client.get("/uretici/urunler/99999/duzenle").status_code
    assert existing == missing == 404


# --- Toplu atama (mass assignment): formda olmayan alanlar değiştirilemez --------------------------

def test_producer_cannot_verify_self_or_set_reputation(client):
    profile = make_producer("ciftci@test.com")
    login(client, "ciftci@test.com")
    client.post("/uretici/profil", data={
        "full_name": "Ali", "farm_name": "Yeni Ad", "region": "Bingöl",
        "is_verified": "y", "reputation_score": "5", "review_count": "999", "user_id": "1",
    })
    db.session.expire_all()
    profile = db.session.get(ProducerProfile, profile.id)
    assert profile.farm_name == "Yeni Ad"
    assert profile.is_verified is False and profile.reputation_score == 0 and profile.review_count == 0


def test_customer_cannot_change_role_or_email_via_account_form(client):
    make_customer("musteri@test.com")
    login(client, "musteri@test.com")
    client.post("/hesabim", data={"full_name": "Zeynep", "email": "admin@test.com", "role_id": "1",
                                  "is_active_account": ""})
    db.session.expire_all()
    user = User.query.filter_by(email="musteri@test.com").one()
    assert user.full_name == "Zeynep" and user.is_customer and user.is_active


def test_svg_upload_is_rejected(client):
    profile = make_producer("ciftci@test.com")
    login(client, "ciftci@test.com")
    from app.models import Category
    page = text(client.post("/uretici/urunler/yeni", data={
        "name": "Domates", "category_id": str(Category.query.filter_by(slug="domates").one().id), "unit": "kg",
        "stock_quantity": "5", "is_active": "y",
        "image": (io.BytesIO(b"<svg onload=alert(1)></svg>"), "resim.svg"),
    }, content_type="multipart/form-data"))
    assert "Yalnızca JPG, PNG veya WEBP" in page and not profile.products


# =====================================================================================
# 6. Kaba kuvvet ve spam koruması
# =====================================================================================

def test_account_locks_after_repeated_failed_logins(client):
    make_customer("musteri@test.com")
    for _ in range(5):
        client.post("/auth/login", data={"email": "musteri@test.com", "password": "YanlisParola1"})

    response = client.post("/auth/login", data={"email": "musteri@test.com", "password": "Parola123"})
    assert response.status_code == 429 and "çok fazla hatalı deneme" in text(response)
    assert client.get("/musteri/panel").status_code == 302  # doğru parolaya rağmen giriş yok

    make_customer("diger@test.com")                          # diğer hesaplar etkilenmez
    assert client.post("/auth/login", data={"email": "diger@test.com", "password": "Parola123"}).status_code == 302


def test_successful_login_resets_failure_counter(client):
    make_customer("musteri@test.com")
    for _ in range(2):
        for _ in range(4):
            client.post("/auth/login", data={"email": "musteri@test.com", "password": "Yanlis1234"})
        assert client.post("/auth/login", data={"email": "musteri@test.com",
                                                "password": "Parola123"}).status_code == 302
        client.post("/auth/logout")


def test_login_attempts_are_limited_per_ip(client, app):
    app.config["LOGIN_ATTEMPTS_PER_IP_PER_MIN"] = 3
    for i in range(3):
        client.post("/auth/login", data={"email": f"x{i}@test.com", "password": "Parola123"})
    assert client.post("/auth/login", data={"email": "x9@test.com", "password": "Parola123"}).status_code == 429


def test_registration_spam_is_limited(client, app):
    app.config["REGISTRATIONS_PER_IP_PER_HOUR"] = 2
    for i in range(2):
        client.post("/auth/register", data={"role": "customer", "full_name": "Spam Kişi", "email": f"s{i}@test.com",
                                            "password": "Parola123", "confirm_password": "Parola123",
                                            "accept_terms": "y"})
    response = client.post("/auth/register", data={"role": "customer", "full_name": "Spam Kişi",
                                                   "email": "s9@test.com", "password": "Parola123",
                                                   "confirm_password": "Parola123", "accept_terms": "y"})
    assert response.status_code == 429 and User.query.count() == 2


def test_cart_add_is_rate_limited(client, app):
    app.config["CART_ADDS_PER_MIN"] = 2
    profile = make_producer("ciftci@test.com")
    listing = make_listing(profile, make_product(profile))
    make_customer("musteri@test.com")
    login(client, "musteri@test.com")
    for _ in range(2):
        client.post(f"/sepet/ekle/{listing.id}", data={"quantity": "1"})
    assert client.post(f"/sepet/ekle/{listing.id}", data={"quantity": "1"}).status_code == 429


def test_unknown_email_costs_the_same_password_check(app):
    """Kullanıcı yoksa da parola hash'i kontrol edilir: yanıt süresi e-postanın kayıtlı olup olmadığını ele vermez."""
    from app.services import auth_service
    with patch("app.services.auth_service.check_password_hash", return_value=False) as checker:
        assert auth_service.authenticate("yok@test.com", "Parola123") is None
    assert checker.call_count == 1


# =====================================================================================
# 7. Oturum ve yapılandırma
# =====================================================================================

def test_production_refuses_default_or_short_secret_key(monkeypatch):
    from config import DEV_SECRET_KEY, ProductionConfig
    monkeypatch.setattr(ProductionConfig, "SECRET_KEY", DEV_SECRET_KEY)
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app("production")
    monkeypatch.setattr(ProductionConfig, "SECRET_KEY", "kisa")
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app("production")
    monkeypatch.setattr(ProductionConfig, "SECRET_KEY", "x" * 64)
    assert create_app("production").config["SESSION_COOKIE_SECURE"] is True


def test_session_protection_is_strong():
    assert login_manager.session_protection == "strong"


def test_tampered_session_user_id_is_treated_as_anonymous(client):
    with client.session_transaction() as session:
        session["_user_id"] = "1 OR 1=1"
    assert client.get("/panel").status_code == 302


# =====================================================================================
# 8. Performans: N+1 sorgu ve indeksler
#    Sayfa başına SQL sorgu sayısı, listedeki kayıt sayısından BAĞIMSIZ olmalı.
# =====================================================================================

def query_count(client, url):
    db.session.expire_all()  # Önceden yüklenmiş nesneler yeniden okunmak zorunda: tembel yüklemeler gizlenmesin
    response = client.get(url)
    assert response.status_code == 200, url
    return int(response.headers["X-Query-Count"])


def add_listings(profile, count, start=0):
    for i in range(start, start + count):
        make_listing(profile, make_product(profile, name=f"Ürün {i}"), title=f"İlan {i}")


def test_market_page_query_count_does_not_grow_with_listings(client):
    profile = make_producer("ciftci@test.com")
    add_listings(profile, 2)
    few = query_count(client, "/pazar/")
    add_listings(profile, 8, start=2)
    many = query_count(client, "/pazar/")
    assert many == few, f"2 ilanda {few}, 10 ilanda {many} sorgu: N+1 var"


def place_orders(count, customer, listing):
    for _ in range(count):
        cart_service.add_to_cart(customer, listing.id, Decimal("1"))
        order_service.place_order(customer, ADDRESS)


def test_order_lists_query_count_does_not_grow(client):
    profile = make_producer("ciftci@test.com")
    listing = make_listing(profile, make_product(profile, stock="100"), quantity="100")
    customer = make_customer("musteri@test.com")
    place_orders(2, customer, listing)

    login(client, "musteri@test.com")
    customer_few = query_count(client, "/siparisler/")
    login(client, "ciftci@test.com")
    producer_few = query_count(client, "/uretici/siparisler")

    place_orders(6, customer, listing)
    login(client, "musteri@test.com")
    assert query_count(client, "/siparisler/") == customer_few
    login(client, "ciftci@test.com")
    assert query_count(client, "/uretici/siparisler") == producer_few


def test_cart_page_query_count_does_not_grow(client):
    profile = make_producer("ciftci@test.com")
    customer = make_customer("musteri@test.com")
    listing = make_listing(profile, make_product(profile, name="Ürün A"))
    cart_service.add_to_cart(customer, listing.id, Decimal("1"))
    login(client, "musteri@test.com")
    few = query_count(client, "/sepet/")
    for i in range(4):
        other = make_listing(profile, make_product(profile, name=f"Ürün {i}"))
        cart_service.add_to_cart(customer, other.id, Decimal("1"))
    assert query_count(client, "/sepet/") == few


def test_admin_categories_and_price_pages_query_count(client):
    from app.services import price_service
    from app.services.auth_service import create_admin_user
    create_admin_user("Yönetici", "admin@test.com", "Yonetici123")
    profile = make_producer("ciftci@test.com")
    make_product(profile, slug="domates")
    price_service.backfill(3)
    login(client, "admin@test.com", "Yonetici123")

    categories_few = query_count(client, "/yonetici/kategoriler")
    prices = query_count(client, "/fiyatlar/")
    for slug in ("biber", "patates", "elma", "uzum"):
        make_product(profile, slug=slug, name=f"Ürün {slug}")
    assert query_count(client, "/yonetici/kategoriler") == categories_few
    assert prices <= 15  # 8 ürünlük fiyat tablosu + tahminler, ürün sayısından bağımsız sabit sorgu


def test_expected_indexes_exist(app):
    inspector = inspect(db.engine)

    def index_columns(table):
        return {tuple(index["column_names"]) for index in inspector.get_indexes(table)}

    assert ("status", "created_at") in index_columns("listings")
    assert ("product_id",) in index_columns("listings")
    assert ("category_id",) in index_columns("products")
    assert ("customer_id", "created_at") in index_columns("orders")
    assert ("listing_id",) in index_columns("order_items")
    assert ("category_id", "price_date") in index_columns("market_prices")
    assert ("product_id", "model_name", "target_date") in index_columns("price_predictions")
    assert ("role_id",) in index_columns("users")
