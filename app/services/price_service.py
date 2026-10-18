"""Piyasa fiyatı iş mantığı (Hafta 9).

- sync_prices(): Sağlayıcıdan bir günün fiyatlarını çeker, doğrular ve market_prices
  tablosuna yazar. Aynı gün tekrar çekilirse kopya oluşmaz, kayıt güncellenir (upsert).
- backfill(): Geriye dönük N günü doldurur (Hafta 10'daki yapay zekâ modeli geçmiş veri ister).
- reference_price_for(): Bir ürünün kategorisine ait en güncel hal ortalaması;
  ilan formunda ve ilan detayında "piyasa karşılaştırması" olarak gösterilir.

Hata politikası: Sağlayıcıya ulaşılamazsa HİÇBİR şey yazılmaz (yarım veri yok) ve
kullanıcıya anlaşılır bir ServiceError döner. Bozuk tek bir satır ise atlanır ve sayılır.
"""
from datetime import date, timedelta
from decimal import Decimal

from flask import current_app

from app.integrations.errors import IntegrationError, RateLimitExceeded
from app.integrations.price_api import get_price_provider
from app.models import Category, MarketPrice
from app.repositories.price_repository import PriceRepository
from app.services.category_service import slugify
from app.services.errors import ServiceError


def _category_map():
    """{slug: kategori id}  — "Domates" fiyatını "domates" kategorisine bağlamak için."""
    return {c.slug: c.id for c in Category.query.all()}


def _is_valid(quote):
    if quote.avg_price <= 0 or quote.min_price <= 0 or quote.max_price <= 0:
        return False
    return quote.min_price <= quote.avg_price <= quote.max_price


def sync_prices(day=None, provider=None):
    """Bir günün fiyatlarını çekip kaydeder. Özet sözlük döndürür."""
    day = day or date.today()
    provider = provider or get_price_provider()

    try:
        quotes = provider.fetch_daily_prices(day)
    except RateLimitExceeded as error:
        raise ServiceError(f"Fiyat servisi hız sınırına ulaşıldı; {error.retry_after or 60} sn sonra tekrar deneyin.")
    except IntegrationError as error:
        current_app.logger.error("Fiyat senkronu başarısız: %s", error.message)
        raise ServiceError(f"Fiyat servisine ulaşılamadı: {error.message}")

    categories = _category_map()
    summary = {"date": day, "fetched": len(quotes), "inserted": 0, "updated": 0, "invalid": 0,
               "source": provider.source}
    try:
        for quote in quotes:
            if not _is_valid(quote):
                summary["invalid"] += 1
                continue
            record = PriceRepository.get_quote(quote.product_name, quote.source, quote.price_date)
            if record is None:
                record = MarketPrice(product_name=quote.product_name, source=quote.source,
                                     price_date=quote.price_date)
                PriceRepository.add(record)
                summary["inserted"] += 1
            else:
                summary["updated"] += 1
            record.unit = quote.unit
            record.min_price = quote.min_price
            record.max_price = quote.max_price
            record.avg_price = quote.avg_price
            record.category_id = categories.get(slugify(quote.product_name))
        PriceRepository.commit()
    except Exception:
        PriceRepository.rollback()
        raise

    current_app.logger.info("Fiyat senkronu: %s", summary)
    return summary


def backfill(days, provider=None, end=None):
    """Son `days` günün fiyatlarını (bugün dahil) çeker."""
    end = end or date.today()
    totals = {"days": 0, "inserted": 0, "updated": 0, "invalid": 0}
    for offset in range(days - 1, -1, -1):
        result = sync_prices(end - timedelta(days=offset), provider)
        totals["days"] += 1
        for key in ("inserted", "updated", "invalid"):
            totals[key] += result[key]
    return totals


# --- Gösterim -----------------------------------------------------------------------------

def latest_board(search=None):
    """Fiyatlar sayfası: en son günün fiyatları + bir önceki kayda göre değişim yüzdesi."""
    day = PriceRepository.latest_date()
    if day is None:
        return {"date": None, "rows": []}

    rows = []
    for record in PriceRepository.for_date(day, (search or "").strip() or None):
        previous = PriceRepository.previous_for(record.product_name, day)
        change = None
        if previous is not None and previous.avg_price:
            change = ((Decimal(record.avg_price) - Decimal(previous.avg_price))
                      / Decimal(previous.avg_price) * 100).quantize(Decimal("0.1"))
        rows.append({"price": record, "change": change})
    return {"date": day, "rows": rows}


def reference_price_for(product):
    """Ürünün kategorisindeki en güncel hal fiyatı (yoksa None)."""
    if product is None or product.category_id is None:
        return None
    return PriceRepository.latest_for_category(product.category_id)


def compare_listing(listing):
    """İlan fiyatı hal ortalamasından yüzde kaç farklı? Birim farklıysa karşılaştırma yapılmaz."""
    reference = reference_price_for(listing.product)
    if reference is None or reference.unit != listing.product.unit:
        return None
    diff = ((Decimal(listing.price) - Decimal(reference.avg_price)) / Decimal(reference.avg_price) * 100)
    return {"reference": reference, "diff_percent": diff.quantize(Decimal("0.1"))}


def status():
    return {"count": PriceRepository.count(), "latest_date": PriceRepository.latest_date(),
            "mock": current_app.config["USE_MOCK_APIS"]}
