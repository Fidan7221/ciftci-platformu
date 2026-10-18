"""Hafta 10 testleri: yapay zekâ fiyat tahmini.

Bölüm 1 — Algoritma (app/ai/): veri tabanı ve Flask olmadan, elle kurulan serilerle.
          Sonucu önceden bilinen seriler kullanılır: düzgün artan seride trend "up" olmalı vb.
Bölüm 2 — Servis + veri tabanı + sayfalar: tahminlerin kaydedilmesi ve arayüzde gösterilmesi.

Çalıştırma: pytest -v tests/test_ai.py
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.ai import sell_advisor
from app.ai.trend_model import (
    DOWN, STABLE, UP, InsufficientDataError, PricePoint, backtest, clip_outliers, fit_linear, forecast,
    prepare_series,
)

END = date(2026, 10, 19)


def series(values, end=END, step=1):
    """values[-1] = son gün (END). step=2 ise gün atlayarak (eksik günlü veri)."""
    n = len(values)
    return [PricePoint(end - timedelta(days=(n - 1 - i) * step), v) for i, v in enumerate(values)]


def linear(start, per_day, days=30):
    return series([start + per_day * i for i in range(days)])


def noisy_flat(level=20.0, days=30):
    pattern = [0.2, -0.15, 0.1, -0.2, 0.05, -0.05, 0.15]
    return series([level + pattern[i % 7] for i in range(days)])


# =====================================================================================
# Bölüm 1: Algoritma
# =====================================================================================

def test_perfect_increasing_line_is_predicted_exactly():
    result = forecast(linear(20, 0.3), horizon_days=7)
    # Son gün 20 + 0.3*29 = 28.7  ->  7 gün sonra 28.7 + 2.1 = 30.8
    assert result.predicted_price == pytest.approx(30.8, abs=0.01)
    assert result.trend == UP
    assert result.slope_per_day == pytest.approx(0.3, abs=1e-4)
    assert result.r2 == pytest.approx(1.0)
    assert result.target_date == END + timedelta(days=7)
    assert result.confidence == 1.0           # geri test hatası 0, veri tam


def test_decreasing_series_is_down():
    result = forecast(linear(40, -0.4))
    assert result.trend == DOWN
    assert result.predicted_price < result.current_price


def test_flat_noisy_series_is_stable_with_good_confidence():
    result = forecast(noisy_flat())
    assert result.trend == STABLE
    assert abs(result.weekly_change_pct) < 2.0
    # Düz seride R² düşüktür ama tahmin yine de isabetlidir: güven R²'ye değil geri teste dayanır
    assert result.confidence >= 0.7


def test_prediction_interval_contains_prediction():
    result = forecast(noisy_flat())
    assert result.lower < result.predicted_price < result.upper


def test_insufficient_data_raises():
    with pytest.raises(InsufficientDataError):
        forecast(linear(20, 0.1, days=10), min_points=14)


def test_gaps_in_dates_are_handled():
    # Gün aşırı veri (eksik günler): eğim yine günlük olarak doğru hesaplanmalı
    points = series([20 + 0.2 * 2 * i for i in range(15)], step=2)
    slope, _, r2, _ = fit_linear(prepare_series(points, window_days=30))
    assert slope == pytest.approx(0.2, abs=1e-6) and r2 == pytest.approx(1.0)


def test_only_window_days_are_used():
    old = series([100.0] * 30, end=END - timedelta(days=60))  # çok eski, alakasız veri
    result = forecast(old + linear(20, 0.3), window_days=30)
    assert result.n_points == 30 and result.predicted_price == pytest.approx(30.8, abs=0.01)


def test_duplicate_days_are_averaged_and_invalid_prices_dropped():
    points = [PricePoint(END, 10.0), PricePoint(END, 20.0), PricePoint(END - timedelta(days=1), 0),
              PricePoint(END - timedelta(days=2), None)]
    prepared = prepare_series(points, window_days=30)
    assert prepared == [PricePoint(END, 15.0)]


def test_outlier_is_clipped():
    values = [20.0 + (0.1 if i % 2 else -0.1) for i in range(30)]
    values[15] = 500.0  # veri giriş hatası
    cleaned = clip_outliers(series(values))
    assert max(p.price for p in cleaned) < 25
    assert forecast(series(values)).trend == STABLE  # tek hatalı değer trendi bozmamalı


def test_predicted_price_never_negative():
    result = forecast(linear(10, -0.5))  # 30 günde 10 -> -4.5'e inen (gerçekçi olmayan) seri
    assert result.predicted_price > 0 and result.lower > 0


def test_backtest_model_beats_naive_on_trending_series():
    model_mape, naive_mape = backtest(prepare_series(linear(20, 0.3), 30), horizon_days=7, window_days=30)
    assert model_mape == pytest.approx(0.0, abs=1e-9)
    assert naive_mape > 0.05  # "fiyat değişmez" varsayımı artan seride yanılır


def test_backtest_returns_none_without_enough_history():
    assert backtest(prepare_series(linear(20, 0.3, days=12), 30), horizon_days=7, window_days=30) == (None, None)


def test_more_noise_means_lower_confidence():
    smooth = forecast(linear(20, 0.2))
    jagged = forecast(series([20 + 0.2 * i + (3 if i % 2 else -3) for i in range(30)]))
    assert jagged.confidence < smooth.confidence


def test_deterministic():
    assert forecast(noisy_flat()) == forecast(noisy_flat())


# --- Öneri kuralları -------------------------------------------------------------------------

def test_rising_prices_suggest_waiting():
    advice = sell_advisor.advise(forecast(linear(20, 0.3)), perishable=False)
    assert advice.action == sell_advisor.WAIT and "artış" in advice.headline
    assert "bozulan" not in advice.detail


def test_perishable_products_get_a_warning():
    advice = sell_advisor.advise(forecast(linear(20, 0.3)), perishable=True)
    assert "bozulan" in advice.detail


def test_falling_prices_suggest_selling_now():
    assert sell_advisor.advise(forecast(linear(40, -0.4))).action == sell_advisor.SELL_NOW


def test_low_confidence_gives_no_timing_advice():
    advice = sell_advisor.advise(forecast(linear(20, 0.3)), min_confidence=1.01)
    assert advice.action == sell_advisor.LOW_CONFIDENCE


def test_price_band_order_and_organic_premium():
    result = forecast(noisy_flat())
    normal = sell_advisor.price_band(result)
    organic = sell_advisor.price_band(result, is_organic=True)
    assert normal[0] < normal[1] < normal[2]
    assert organic[1] > normal[1] and organic[0] == normal[0]  # taban aynı, önerilen ve tavan daha yüksek


def test_band_follows_forecast_by_confidence():
    result = forecast(linear(20, 0.3))           # güven 1.0: temel = tahmin edilen fiyat
    low, _, _ = sell_advisor.price_band(result)
    assert low == pytest.approx(result.predicted_price, abs=0.01)


# =====================================================================================
# Bölüm 2: Servis, veri tabanı ve arayüz
# =====================================================================================

from app.models import MarketPrice, PricePrediction  # noqa: E402
from app.services import prediction_service, price_service  # noqa: E402
from tests.conftest import login, make_customer, make_listing, make_producer, make_product  # noqa: E402


def seed_prices(app, category_slug="domates", days=30, start=20.0, per_day=0.3, name="Domates"):
    """Bugüne kadar düzgün artan hal fiyatı serisi yazar (servis üzerinden değil, doğrudan)."""
    from app.extensions import db
    from app.models import Category
    category = Category.query.filter_by(slug=category_slug).one()
    today = date.today()
    for i in range(days):
        price = Decimal(str(round(start + per_day * i, 2)))
        db.session.add(MarketPrice(product_name=name, source="test", category=category, unit="kg",
                                   min_price=price - 1, max_price=price + 1, avg_price=price,
                                   price_date=today - timedelta(days=days - 1 - i)))
    db.session.commit()
    return category


def test_forecast_for_category_reads_from_database(app):
    category = seed_prices(app)
    result = prediction_service.forecast_for_category(category.id)
    assert result.trend == UP and result.n_points == 30
    assert result.target_date == date.today() + timedelta(days=7)


def test_category_without_data_returns_none(app):
    seed_prices(app, days=5)
    from app.models import Category
    assert prediction_service.forecast_for_category(Category.query.filter_by(slug="domates").one().id) is None


def test_generate_predictions_saves_rows_and_is_idempotent(app):
    seed_prices(app)
    profile = make_producer("ciftci@test.com")
    make_product(profile, name="Salkım Domates")
    make_product(profile, name="Çarliston Biber", slug="biber")  # biber için fiyat verisi yok

    summary = prediction_service.generate_predictions()
    assert summary == {"products": 2, "saved": 1, "skipped": 1}

    prediction = PricePrediction.query.one()
    assert prediction.trend == "up" and prediction.model_name == prediction_service.MODEL_NAME
    assert prediction.predicted_price > prediction.current_price
    assert prediction.suggested_min_price < prediction.suggested_price < prediction.suggested_max_price
    assert 0 <= prediction.confidence <= 1

    prediction_service.generate_predictions()       # aynı gün tekrar: kopya yok, güncelleme
    assert PricePrediction.query.count() == 1


def test_predict_prices_cli(app):
    seed_prices(app)
    make_product(make_producer("ciftci@test.com"))
    result = app.test_cli_runner().invoke(args=["predict-prices"])
    assert "1 tahmin kaydedildi" in result.output


def test_prediction_for_product_writes_once_per_target_day(app):
    seed_prices(app)
    product = make_product(make_producer("ciftci@test.com"))
    first, insight = prediction_service.prediction_for_product(product)
    second, _ = prediction_service.prediction_for_product(product)
    assert first.id == second.id and insight["advice"].action == sell_advisor.WAIT


def test_chart_payload_shapes(app):
    category = seed_prices(app)
    payload = prediction_service.chart_payload(prediction_service.forecast_for_category(category.id))
    n = len(payload["labels"])
    assert n == 30 + 7                                       # 30 gün geçmiş + 7 gün tahmin
    assert all(len(payload[key]) == n for key in ("actual", "predicted", "lower", "upper"))
    assert payload["actual"][-1] is None and payload["predicted"][0] is None
    assert payload["lower"][-1] <= payload["predicted"][-1] <= payload["upper"][-1]


def test_producer_dashboard_shows_ai_card(client, app):
    seed_prices(app)
    profile = make_producer("ciftci@test.com")
    make_product(profile, name="Salkım Domates")
    login(client, "ciftci@test.com")
    page = client.get("/uretici/panel").get_data(as_text=True)
    assert "yapay zekâ önerileri" in page and "Önerilen doğrudan satış fiyatı" in page
    assert 'data-price-chart="uretici-grafik-1-veri"' in page
    assert PricePrediction.query.count() == 1               # panel açılınca tahmin kaydedildi


def test_producer_dashboard_without_data_shows_hint(client):
    profile = make_producer("ciftci@test.com")
    make_product(profile)
    login(client, "ciftci@test.com")
    assert "yeterli hal fiyatı verisi yok" in client.get("/uretici/panel").get_data(as_text=True)


def test_listing_form_offers_suggested_price(client, app):
    seed_prices(app)
    profile = make_producer("ciftci@test.com")
    product = make_product(profile)
    login(client, "ciftci@test.com")
    page = client.get("/uretici/ilanlar/yeni").get_data(as_text=True)
    assert "Önerilen fiyatı kullan" in page and f'"{product.id}": {{"confidence"' in page


def test_customer_dashboard_shows_market_trends(client, app):
    seed_prices(app)
    make_customer("musteri@test.com")
    login(client, "musteri@test.com")
    page = client.get("/musteri/panel").get_data(as_text=True)
    assert "Bu hafta hal fiyatları" in page and "yükseliş eğiliminde" in page
    assert "Önerilen doğrudan satış" not in page   # satış önerisi yalnızca üreticiye


def test_price_detail_page_and_table_column(client, app):
    seed_prices(app)
    page = client.get("/fiyatlar/domates").get_data(as_text=True)
    assert "Model özeti" in page and "Doğrusal regresyon" in page and "Geri test hatası" in page
    assert "7 gün tahmini" in client.get("/fiyatlar/").get_data(as_text=True)
    assert client.get("/fiyatlar/olmayan-urun").status_code == 404


def test_listing_detail_shows_trend_card(client, app):
    seed_prices(app)
    profile = make_producer("ciftci@test.com")
    listing = make_listing(profile, make_product(profile))
    page = client.get(f"/pazar/ilan/{listing.id}").get_data(as_text=True)
    assert 'data-price-chart="ilan-grafik-veri"' in page and "yükseliş eğiliminde" in page
