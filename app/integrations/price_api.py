"""Hal / piyasa fiyatı sağlayıcıları (Hafta 9).

Tasarım: "Strateji" ve "Adaptör" desenleri
- PriceProvider ortak arayüzdür: fetch_daily_prices(gün) -> [PriceQuote]
- MockPriceProvider: İnternete çıkmadan gerçekçi, TEKRARLANABİLİR fiyatlar üretir
  (aynı gün + aynı ürün = hep aynı fiyat). Ders, demo ve testler için.
- HttpPriceProvider: Gerçek bir JSON fiyat servisine bağlanır. Her kaynağın veri
  biçimi farklı olduğundan, yalnızca _parse_item() metodunu o kaynağa uyarlamak yeterlidir.
Servis katmanı hangi sağlayıcının kullanıldığını bilmez; get_price_provider() seçer.
"""
import hashlib
import math
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from flask import current_app

from app.integrations.errors import ConfigurationError, ExternalServiceError
from app.integrations.http_client import ApiClient
from app.utils.rate_limit import RateLimiter

TWO_PLACES = Decimal("0.01")


@dataclass(frozen=True)
class PriceQuote:
    """Sağlayıcıdan bağımsız, normalize edilmiş tek bir fiyat kaydı."""

    product_name: str
    unit: str
    min_price: Decimal
    max_price: Decimal
    avg_price: Decimal
    price_date: date
    source: str


class PriceProvider(ABC):
    source = "unknown"

    @abstractmethod
    def fetch_daily_prices(self, day):
        """Verilen günün fiyatlarını PriceQuote listesi olarak döndürür."""


# --- 1) Sahte sağlayıcı --------------------------------------------------------------

class MockPriceProvider(PriceProvider):
    """Mevsimsel dalgalanma + küçük günlük gürültü ile hal fiyatı benzetimi."""

    source = "mock_hal"

    # Ürün: (temel ortalama TL/kg, en verimli hasat ayı)
    BASE_PRICES = {
        "Domates": (24, 8), "Biber": (32, 8), "Patates": (14, 10), "Elma": (20, 10),
        "Üzüm": (38, 9), "Kayısı": (55, 7), "Nohut": (58, 9), "Fasulye": (72, 9),
    }

    def fetch_daily_prices(self, day):
        quotes = []
        for name, (base, harvest_month) in self.BASE_PRICES.items():
            # hashlib ile sabit tohum: Python'un hash() fonksiyonu her çalıştırmada değişir, bu değişmez
            seed = int(hashlib.md5(f"{name}-{day.isoformat()}".encode()).hexdigest(), 16)
            rng = random.Random(seed)

            # Hasat ayında fiyat en düşük, 6 ay sonra en yüksek (±%25)
            phase = 2 * math.pi * (day.timetuple().tm_yday - harvest_month * 30.4) / 365
            seasonal = 1 - 0.25 * math.cos(phase)
            noise = rng.uniform(-0.04, 0.04)
            avg = Decimal(str(base * seasonal * (1 + noise))).quantize(TWO_PLACES)
            spread = Decimal(str(rng.uniform(0.10, 0.20)))
            quotes.append(PriceQuote(
                product_name=name, unit="kg",
                min_price=(avg * (1 - spread)).quantize(TWO_PLACES),
                max_price=(avg * (1 + spread)).quantize(TWO_PLACES),
                avg_price=avg, price_date=day, source=self.source,
            ))
        return quotes


# --- 2) Gerçek HTTP sağlayıcı (adaptör) ---------------------------------------------------

class HttpPriceProvider(PriceProvider):
    """Beklenen yanıt biçimi (kaynağa göre _parse_item uyarlanır):

    GET {PRICE_API_URL}/prices?date=2026-10-19
    {"date": "2026-10-19",
     "items": [{"name": "Domates", "unit": "kg", "min": 18.0, "max": 30.0, "avg": 24.5}, ...]}
    """

    source = "hal_api"

    def __init__(self, client):
        self.client = client

    def fetch_daily_prices(self, day):
        payload = self.client.get_json("/prices", params={"date": day.isoformat()})
        items = payload.get("items") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            raise ExternalServiceError("Fiyat servisi beklenmeyen biçimde yanıt verdi.", service=self.source)

        quotes = []
        for raw in items:
            quote = self._parse_item(raw, day)
            if quote is not None:
                quotes.append(quote)
        return quotes

    def _parse_item(self, raw, day):
        """Tek satırı PriceQuote'a çevirir; bozuk satırı atlar (None) ama tüm işlemi durdurmaz."""
        try:
            name = str(raw["name"]).strip()
            avg = Decimal(str(raw["avg"])).quantize(TWO_PLACES)
            low = Decimal(str(raw.get("min", raw["avg"]))).quantize(TWO_PLACES)
            high = Decimal(str(raw.get("max", raw["avg"]))).quantize(TWO_PLACES)
        except (KeyError, TypeError, InvalidOperation):
            current_app.logger.warning("Fiyat satırı atlandı (biçim hatası): %r", raw)
            return None
        if not name:
            return None
        return PriceQuote(product_name=name, unit=str(raw.get("unit") or "kg"), min_price=low,
                          max_price=high, avg_price=avg, price_date=day, source=self.source)


# --- Seçici ---------------------------------------------------------------------------------

def get_price_provider():
    """Ayarlara göre sahte ya da gerçek sağlayıcıyı döndürür (uygulama başına tek örnek)."""
    cached = current_app.extensions.get("price_provider")
    if cached is not None:
        return cached

    config = current_app.config
    if config["USE_MOCK_APIS"]:
        provider = MockPriceProvider()
    else:
        if not config["PRICE_API_URL"]:
            raise ConfigurationError("PRICE_API_URL tanımlı değil (.env).", service="hal_api")
        client = ApiClient(
            config["PRICE_API_URL"], config["PRICE_API_KEY"] or None, name="hal_api",
            timeout=config["PRICE_API_TIMEOUT"], max_retries=2,
            rate_limiter=RateLimiter(config["PRICE_API_RATE_LIMIT_PER_MINUTE"], 60),
        )
        provider = HttpPriceProvider(client)

    current_app.extensions["price_provider"] = provider
    return provider
