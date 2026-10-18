"""Hafta 5 testleri: kayıt, giriş, çıkış ve rol tabanlı erişim.

Çalıştırma: pytest -v tests/test_auth.py
"""
from app.models import RoleName
from app.repositories.user_repository import UserRepository

CUSTOMER = {
    "role": RoleName.CUSTOMER,
    "full_name": "Ayşe Müşteri",
    "email": "Ayse@Test.com",
    "password": "Parola123",
    "confirm_password": "Parola123",
    "accept_terms": "y",
}

PRODUCER = {
    **CUSTOMER,
    "role": RoleName.PRODUCER,
    "full_name": "Mehmet Çiftçi",
    "email": "mehmet@test.com",
    "farm_name": "Genç Organik Çiftliği",
    "region": "Bingöl / Genç",
}


def register(client, data):
    return client.post("/auth/register", data=data, follow_redirects=True)


def login(client, email, password="Parola123"):
    return client.post("/auth/login", data={"email": email, "password": password},
                       follow_redirects=True)


# --- Kayıt ---------------------------------------------------------------

def test_register_customer_creates_user_and_cart(client):
    response = register(client, CUSTOMER)
    assert "Kaydınız oluşturuldu" in response.get_data(as_text=True)

    user = UserRepository.get_by_email("ayse@test.com")  # e-posta küçük harfe çevrildi
    assert user is not None and user.is_customer
    assert user.cart is not None
    assert user.password_hash != "Parola123"  # parola hash'lendi


def test_register_producer_creates_profile(client):
    register(client, PRODUCER)
    user = UserRepository.get_by_email("mehmet@test.com")
    assert user.is_producer
    assert user.producer_profile.farm_name == "Genç Organik Çiftliği"


def test_producer_requires_farm_name(client):
    data = {**PRODUCER, "farm_name": ""}
    response = register(client, data)
    assert "çiftlik adı zorunludur" in response.get_data(as_text=True)
    assert UserRepository.get_by_email("mehmet@test.com") is None


def test_duplicate_email_rejected(client):
    register(client, CUSTOMER)
    response = register(client, CUSTOMER)
    assert "zaten var" in response.get_data(as_text=True)


def test_weak_password_rejected(client):
    data = {**CUSTOMER, "password": "sadeceharf", "confirm_password": "sadeceharf"}
    response = register(client, data)
    assert "harf ve bir rakam" in response.get_data(as_text=True)


def test_cannot_self_register_as_admin(client):
    data = {**CUSTOMER, "role": RoleName.ADMIN}
    register(client, data)
    assert UserRepository.get_by_email("ayse@test.com") is None


# --- Giriş / çıkış -------------------------------------------------------

def test_login_success_redirects_to_role_panel(client):
    register(client, PRODUCER)
    response = login(client, "mehmet@test.com")
    page = response.get_data(as_text=True)
    assert "Üretici Paneli" in page


def test_login_wrong_password(client):
    register(client, CUSTOMER)
    response = login(client, "ayse@test.com", "YanlisParola1")
    assert "E-posta veya parola hatalı" in response.get_data(as_text=True)


def test_logout_requires_post(client):
    register(client, CUSTOMER)
    login(client, "ayse@test.com")
    assert client.get("/auth/logout").status_code == 405  # GET ile çıkış yapılamaz
    response = client.post("/auth/logout", follow_redirects=True)
    assert "Oturumunuz kapatıldı" in response.get_data(as_text=True)


def test_open_redirect_blocked(client):
    register(client, CUSTOMER)
    response = client.post(
        "/auth/login?next=https://kotu-site.com",
        data={"email": "ayse@test.com", "password": "Parola123"},
    )
    assert response.status_code == 302
    assert "kotu-site.com" not in response.headers["Location"]


# --- Rol tabanlı erişim ----------------------------------------------------

def test_anonymous_redirected_to_login(client):
    response = client.get("/uretici/panel")
    assert response.status_code == 302
    assert "/auth/login" in response.headers["Location"]


def test_customer_cannot_open_producer_panel(client):
    register(client, CUSTOMER)
    login(client, "ayse@test.com")
    assert client.get("/uretici/panel").status_code == 403


def test_producer_cannot_open_customer_panel(client):
    register(client, PRODUCER)
    login(client, "mehmet@test.com")
    assert client.get("/musteri/panel").status_code == 403
