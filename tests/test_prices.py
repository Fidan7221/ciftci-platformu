"""Hafta 9 testleri: hal fiyatı servisi, fiyat sayfası ve ilanlarda piyasa karşılaştırması.

Çalıştırma: pytest -v tests/test_prices.py
"""
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from app.integrations.errors import ExternalTimeout, RateLimitExceeded
from app.integrations.price_api import PriceQuote
from app.models import Category, MarketPrice
from app.services import price_service
from app.services.errors import ServiceError
from tests.conftest import login, make_listing, make_producer, make_product

TODAY = date.today()


def quote(name="Domates", avg="24.00", low="20.00", high="28.00", day=TODAY, unit="kg"):
    return PriceQuote(name, unit, Decimal(low), Decimal(high), Decimal(avg), day, "test_kaynak")


def fake_provider(*quotes, error=None):
    provider = MagicMock()
    provider.source = "test_kaynak"
    if error:
        provider.fetch_daily_prices.side_effect = error
    else:
        provider.fetch_daily_prices.return_value = list(quotes)
    return provider


def test_sync_inserts_then_updates_without_duplicates(app):
    summary = price_service.sync_prices(TODAY, fake_provider(quote(), quote("Biber", "35", "30", "40")))
    assert summary["inserted"] == 2 and summary["updated"] == 0

    summary = price_service.sync_prices(TODAY, fake_provider(quote(avg="26.00")))
    assert summary["inserted"] == 0 and summary["updated"] == 1
    assert MarketPrice.query.count() == 2
    assert MarketPrice.query.filter_by(product_name="Domates").one().avg_price == Decimal("26.00")


def test_sync_links_prices_to_categories(app):
    price_service.sync_prices(TODAY, fake_provider(quote("Domates"), quote("Üzüm", "40", "35", "45")))
    domates = Category.query.filter_by(slug="domates").one()
    uzum = Category.query.filter_by(slug="uzum").one()
    assert MarketPrice.query.filter_by(product_name="Domates").one().category_id == domates.id
    assert MarketPrice.query.filter_by(product_name="Üzüm").one().category_id == uzum.id


def test_invalid_rows_are_skipped(app):
    summary = price_service.sync_prices(TODAY, fake_provider(
        quote(), quote("Biber", avg="50", low="30", high="40"), quote("Elma", avg="0", low="0", high="0")))
    assert summary["inserted"] == 1 and summary["invalid"] == 2


@pytest.mark.parametrize("error, message", [
    (ExternalTimeout("zaman aşımı"), "ulaşılamadı"),
    (RateLimitExceeded("çok istek", retry_after=42), "42 sn"),
])
def test_provider_errors_write_nothing(app, error, message):
    with pytest.raises(ServiceError, match=message):
        price_service.sync_prices(TODAY, fake_provider(error=error))
    assert MarketPrice.query.count() == 0


def test_backfill_with_mock_provider_via_cli(app):
    result = app.test_cli_runner().invoke(args=["fetch-prices", "--days", "5"])
    assert result.exit_code == 0, result.output
    days = {p.price_date for p in MarketPrice.query.all()}
    assert days == {TODAY - timedelta(days=offset) for offset in range(5)}
    # Tekrar çalıştırmak kopya oluşturmaz
    app.test_cli_runner().invoke(args=["fetch-prices", "--days", "5"])
    assert len({(p.product_name, p.price_date) for p in MarketPrice.query.all()}) == MarketPrice.query.count()


def test_latest_board_shows_change(app):
    price_service.sync_prices(TODAY - timedelta(days=1), fake_provider(quote(avg="20.00", low="18", high="22",
                                                                               day=TODAY - timedelta(days=1))))
    price_service.sync_prices(TODAY, fake_provider(quote(avg="22.00", low="20", high="24")))
    board = price_service.latest_board()
    assert board["date"] == TODAY
    assert board["rows"][0]["change"] == Decimal("10.0")   # 20 -> 22 = %10 artış


def test_prices_page_public_and_sync_admin_only(client, app):
    price_service.backfill(2)
    page = client.get("/fiyatlar/").get_data(as_text=True)
    assert "Hal Fiyatları" in page and "Domates" in page and "Fiyatları şimdi güncelle" not in page

    make_producer("ciftci@test.com")
    login(client, "ciftci@test.com")
    assert client.post("/fiyatlar/guncelle").status_code == 403


def test_admin_sync_button_and_rate_limit(client, app):
    from app.services.auth_service import create_admin_user
    create_admin_user("Yönetici", "admin@test.com", "Yonetici123")
    login(client, "admin@test.com", "Yonetici123")

    page = client.post("/fiyatlar/guncelle", follow_redirects=True).get_data(as_text=True)
    assert "Fiyatlar güncellendi" in page
    for _ in range(2):
        client.post("/fiyatlar/guncelle")
    assert client.post("/fiyatlar/guncelle").status_code == 429  # dakikada en fazla 3


def test_listing_detail_compares_with_market_price(client):
    price_service.sync_prices(TODAY, fake_provider(quote(avg="25.00", low="20", high="30")))
    profile = make_producer("ciftci@test.com")
    listing = make_listing(profile, make_product(profile, slug="domates"), price="20")

    page = client.get(f"/pazar/ilan/{listing.id}").get_data(as_text=True)
    assert "Hal ortalaması" in page and "%20 altında" in page   # 20 TL, 25 TL'den %20 ucuz


def test_no_comparison_when_units_differ(client):
    price_service.sync_prices(TODAY, fake_provider(quote(avg="25.00")))
    profile = make_producer("ciftci@test.com")
    listing = make_listing(profile, make_product(profile, unit="kasa"), price="200")
    assert price_service.compare_listing(listing) is None


def test_listing_form_shows_market_hint(client):
    price_service.sync_prices(TODAY, fake_provider(quote(avg="25.00")))
    profile = make_producer("ciftci@test.com")
    make_product(profile)
    login(client, "ciftci@test.com")
    page = client.get("/uretici/ilanlar/yeni").get_data(as_text=True)
    assert "25,00" in page  # Hafta 11: veri JS'e tojson ile gider; ₺ işareti \u20ba olarak kaçırılır
