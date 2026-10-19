"""Yapay zekâ tahmin servisi (Hafta 10): model ↔ veri tabanı ↔ arayüz arasındaki köprü.

Katmanlar:
  PriceRepository.daily_series_for_category  ->  app/ai/trend_model.forecast   (tahmin)
                                              ->  app/ai/sell_advisor.advise    (öneri)
                                              ->  PredictionRepository          (kayıt)
                                              ->  şablonlar (kart + grafik)

Model, ürünün KATEGORİSİNE ait hal fiyatı serisiyle çalışır (ör. "Salkım Domates" ürünü ->
"Domates" kategorisinin hal fiyatları). Sonuç her ürün için price_predictions tablosuna yazılır.
"""
from datetime import date, timedelta
from decimal import Decimal

from flask import current_app

from app.ai import sell_advisor, trend_model
from app.ai.trend_model import InsufficientDataError, PricePoint
from app.models import PricePrediction, Product
from app.repositories.prediction_repository import PredictionRepository
from app.repositories.price_repository import PriceRepository
from app.repositories.product_repository import CategoryRepository

MODEL_NAME = "linreg-30g-v1"
PERISHABLE_CATEGORIES = {"sebze", "meyve"}  # hızlı bozulan ürün grupları (üst kategori slug'ı)


def _settings():
    config = current_app.config
    return {
        "horizon_days": config["AI_FORECAST_HORIZON_DAYS"],
        "window_days": config["AI_WINDOW_DAYS"],
        "min_points": config["AI_MIN_POINTS"],
        "stable_threshold_pct": config["AI_STABLE_THRESHOLD_PCT"],
    }


def _is_perishable(category):
    root = category.parent or category
    return root.slug in PERISHABLE_CATEGORIES


# --- Tahmin -------------------------------------------------------------------------------------

def forecast_for_category(category_id):
    """Kategorinin hal fiyatı serisinden tahmin üretir; veri yetersizse None."""
    settings = _settings()
    since = date.today() - timedelta(days=settings["window_days"] * 2)
    rows = PriceRepository.daily_series_for_category(category_id, since)
    try:
        return trend_model.forecast([PricePoint(day, price) for day, price in rows], **settings)
    except InsufficientDataError:
        return None


def forecasts_for_categories(category_ids):
    """Birden çok kategori için tahmin; veri tek sorguda çekilir (Hafta 11). {id: Forecast | None}"""
    settings = _settings()
    since = date.today() - timedelta(days=settings["window_days"] * 2)
    results = {}
    for category_id, rows in PriceRepository.daily_series_for_categories(list(category_ids), since).items():
        try:
            results[category_id] = trend_model.forecast([PricePoint(d, p) for d, p in rows], **settings)
        except InsufficientDataError:
            results[category_id] = None
    return results


def chart_payload(forecast):
    """Chart.js için JSON'a çevrilebilir veri: geçmiş seri + tahmin çizgisi + genişleyen tahmin aralığı."""
    history = {p.day: round(p.price, 2) for p in forecast.history}
    first, last = forecast.history[0].day, forecast.history[-1].day
    last_price = round(forecast.history[-1].price, 2)
    steps = (forecast.target_date - last).days

    labels, actual, predicted, lower, upper = [], [], [], [], []
    day = first
    while day <= forecast.target_date:
        labels.append(day.strftime("%d.%m"))
        actual.append(history.get(day))
        if day < last:
            for series in (predicted, lower, upper):
                series.append(None)
        else:
            ratio = (day - last).days / steps if steps else 1  # 0 (son gözlem) -> 1 (hedef gün)
            predicted.append(round(last_price + ratio * (forecast.predicted_price - last_price), 2))
            lower.append(round(last_price + ratio * (forecast.lower - last_price), 2))
            upper.append(round(last_price + ratio * (forecast.upper - last_price), 2))
        day += timedelta(days=1)

    return {"labels": labels, "actual": actual, "predicted": predicted, "lower": lower, "upper": upper}


def insight_for_category(category, is_organic=False):
    """Bir kategori için kartta gösterilecek her şey; veri yetersizse None."""
    forecast = forecast_for_category(category.id)
    if forecast is None:
        return None
    latest = PriceRepository.latest_for_category(category.id)
    min_confidence = current_app.config["AI_MIN_CONFIDENCE"]
    return {
        "category": category,
        "unit": latest.unit if latest else "kg",
        "forecast": forecast,
        "advice": sell_advisor.advise(forecast, is_organic=is_organic,
                                      perishable=_is_perishable(category), min_confidence=min_confidence),
        "consumer_hint": sell_advisor.consumer_hint(forecast),
        "chart": chart_payload(forecast),
        "data_age_days": (date.today() - forecast.history[-1].day).days,
        "model_name": MODEL_NAME,
    }


# --- Kayıt (price_predictions) -----------------------------------------------------------------------

def _money(value):
    return Decimal(str(value)).quantize(Decimal("0.01"))


def _upsert(product, insight):
    forecast, advice = insight["forecast"], insight["advice"]
    record = PredictionRepository.find(product.id, MODEL_NAME, forecast.target_date)
    if record is None:
        record = PricePrediction(product=product, model_name=MODEL_NAME, target_date=forecast.target_date)
        PredictionRepository.add(record)
    record.predicted_price = _money(forecast.predicted_price)
    record.trend = forecast.trend
    record.confidence = forecast.confidence
    record.recommendation = advice.headline[:255]
    record.action = advice.action
    record.current_price = _money(forecast.current_price)
    record.lower_price = _money(forecast.lower)
    record.upper_price = _money(forecast.upper)
    record.suggested_min_price = _money(advice.suggested_min)
    record.suggested_price = _money(advice.suggested_price)
    record.suggested_max_price = _money(advice.suggested_max)
    record.backtest_mape = forecast.backtest_mape
    return record


def prediction_for_product(product):
    """Ürünün güncel tahmini ve kart verisi: (PricePrediction | None, insight | None).

    Aynı hedef gün için kayıt varsa yeniden yazılmaz (sayfa her açıldığında veri tabanına
    yazmamak için); günün ilk görüntülemesinde ya da `flask predict-prices` ile oluşturulur.
    """
    insight = insight_for_category(product.category, product.is_organic)
    if insight is None:
        return None, None
    record = PredictionRepository.find(product.id, MODEL_NAME, insight["forecast"].target_date)
    if record is None:
        record = _upsert(product, insight)
        PredictionRepository.commit()
    return record, insight


def generate_predictions():
    """Satıştaki tüm ürünler için tahmin üretip kaydeder. Komut: flask predict-prices"""
    cache, summary = {}, {"products": 0, "saved": 0, "skipped": 0}
    products = Product.query.filter_by(is_active=True).order_by(Product.id).all()
    for product in products:
        summary["products"] += 1
        key = (product.category_id, product.is_organic)
        if key not in cache:  # Aynı kategorideki ürünler için modeli bir kez çalıştır
            cache[key] = insight_for_category(product.category, product.is_organic)
        if cache[key] is None:
            summary["skipped"] += 1
            continue
        _upsert(product, cache[key])
        summary["saved"] += 1
    PredictionRepository.commit()
    return summary


# --- Paneller için ------------------------------------------------------------------------------------

def producer_insights(profile, limit=4):
    """Üreticinin satıştaki ürünlerinin kategorileri için tahmin kartları (kategori başına bir kart)."""
    cards, seen = [], set()
    for product in sorted(profile.products, key=lambda p: p.name):
        if not product.is_active or product.category_id in seen:
            continue
        seen.add(product.category_id)
        record, insight = prediction_for_product(product)
        if insight is not None:
            cards.append({"product": product, "prediction": record, "insight": insight})
        if len(cards) >= limit:
            break
    return cards


def market_overview(limit=4):
    """Müşteri paneli: en çok fiyat verisi olan kategorilerin trend özeti."""
    since = date.today() - timedelta(days=current_app.config["AI_WINDOW_DAYS"])
    cards = []
    for category_id in PriceRepository.categories_with_prices(since):
        category = CategoryRepository.get_by_id(category_id)
        insight = insight_for_category(category) if category else None
        if insight is not None:
            cards.append(insight)
        if len(cards) >= limit:
            break
    return cards


def listing_suggestions(profile):
    """İlan formu için: {ürün id: {min, önerilen, max, başlık, güven}}"""
    suggestions = {}
    for product in profile.products:
        if not product.is_active:
            continue
        record, insight = prediction_for_product(product)
        if insight is None or insight["unit"] != product.unit:
            continue  # Hal fiyatı kg, ürün kasa ile satılıyorsa öneri anlamsız olur
        advice = insight["advice"]
        suggestions[product.id] = {
            "min": advice.suggested_min, "price": advice.suggested_price, "max": advice.suggested_max,
            "headline": advice.headline, "confidence": insight["forecast"].confidence,
        }
    return suggestions
