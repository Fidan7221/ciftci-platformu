"""Satış zamanı ve fiyat bandı önerisi (Hafta 10) — saf modül.

Tahmin modeli (trend_model) "fiyat ne olacak?" sorusunu yanıtlar.
Bu modül ise "üretici ne yapmalı?" sorusunu KURALLARLA yanıtlar. Kurallar bilerek
açık ve ayarlanabilir tutuldu: üretici neden bu öneriyi aldığını görebilmeli.

FİYAT BANDI
  temel   = güncel hal seviyesi + güven × (tahmin - güncel)
            (güven düşükse tahmine az, yüksekse çok ağırlık verilir)
  taban   = temel                         -> bunun altı, ürünü aracıya hal fiyatından vermekten kötü
  önerilen= temel × (1 + doğrudan satış primi [+ organik primi])
  tavan   = temel × (1 + en yüksek prim [+ organik primi])
Hal fiyatı TOPTAN fiyattır; doğrudan satışta aracı payı üreticide kaldığı için üretici
hal fiyatının üzerinde satabilir ama perakende fiyatını geçmemelidir.
"""
from dataclasses import dataclass

from app.ai.trend_model import DOWN, UP

DIRECT_SALE_PREMIUM = 0.15   # doğrudan satışta önerilen prim (%15)
MAX_PREMIUM = 0.35           # tavan prim (%35); üstü genelde perakende fiyatını aşar
ORGANIC_PREMIUM = 0.10       # organik ürün için ek prim
MIN_CONFIDENCE = 0.40        # bunun altında "bekle / sat" önerisi verilmez
MIN_GAIN_PCT = 3.0           # beklemeye değmesi için gereken en az artış

WAIT, SELL_NOW, NEUTRAL, LOW_CONFIDENCE = "wait", "sell_now", "neutral", "low_confidence"


@dataclass(frozen=True)
class Advice:
    action: str
    headline: str
    detail: str
    suggested_min: float
    suggested_price: float
    suggested_max: float
    expected_change_pct: float


def _tr(number):
    """4.3 -> "4,3" (Türkçe ondalık ayırıcı)"""
    return f"{number:.1f}".replace(".", ",")


def price_band(forecast, is_organic=False):
    base = forecast.current_price + forecast.confidence * (forecast.predicted_price - forecast.current_price)
    bonus = ORGANIC_PREMIUM if is_organic else 0.0
    return (round(base, 2),
            round(base * (1 + DIRECT_SALE_PREMIUM + bonus), 2),
            round(base * (1 + MAX_PREMIUM + bonus), 2))


def advise(forecast, is_organic=False, perishable=True, min_confidence=MIN_CONFIDENCE):
    low, suggested, high = price_band(forecast, is_organic)
    change = round(forecast.expected_change_pct, 1)
    days = forecast.horizon_days

    if forecast.confidence < min_confidence:
        action = LOW_CONFIDENCE
        headline = "Tahmin güvenilirliği düşük"
        detail = ("Son günlerdeki fiyatlar düzensiz; model net bir yön göremiyor. "
                  "Fiyatınızı güncel hal ortalamasına göre belirleyin ve birkaç gün takip edin.")
    elif forecast.trend == UP and change >= MIN_GAIN_PCT:
        action = WAIT
        headline = f"Fiyat artış eğiliminde: {days} günde yaklaşık %{_tr(change)} artış bekleniyor"
        detail = ("Ürününüz bekletmeye uygunsa satışın bir kısmını birkaç gün ertelemek daha kazançlı olabilir."
                  + (" Dikkat: hızlı bozulan bir ürün; bekleme kaybı artıştan büyük olabilir." if perishable else ""))
    elif forecast.trend == UP:
        action = NEUTRAL
        headline = f"Hafif artış eğilimi: {days} günde yaklaşık %{_tr(change)}"
        detail = "Artış, satışı ertelemeye değecek kadar büyük değil; stok durumunuza göre satış yapabilirsiniz."
    elif forecast.trend == DOWN:
        action = SELL_NOW
        headline = f"Fiyat düşüş eğiliminde: {days} günde yaklaşık %{_tr(abs(change))} düşüş bekleniyor"
        detail = "Elinizdeki stoğu bekletmeden satışa çıkarmanız önerilir."
    else:
        action = NEUTRAL
        headline = "Fiyat dengeli seyrediyor"
        detail = "Belirgin bir artış ya da düşüş beklenmiyor; stok durumunuza göre satış yapabilirsiniz."

    return Advice(action, headline, detail, low, suggested, high, change)


def consumer_hint(forecast):
    """Müşteri paneli için kısa, tarafsız bilgi cümlesi (satın alma tavsiyesi değildir)."""
    if forecast.confidence < MIN_CONFIDENCE:
        return "Fiyatlar dalgalı."
    if forecast.trend == DOWN:
        return "Hal fiyatları düşüş eğiliminde."
    if forecast.trend == UP:
        return "Hal fiyatları yükseliş eğiliminde."
    return "Hal fiyatları dengeli."
