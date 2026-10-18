"""Fiyat trend tahmini (Hafta 10) — Flask'tan ve veri tabanından BAĞIMSIZ saf modül.

Girdi : Tarih + ortalama hal fiyatı listesi (PricePoint)
Çıktı : Forecast — 7 gün sonraki tahmini fiyat, trend yönü, %95 tahmin aralığı, güven skoru

YÖNTEM (açıklanabilir olsun diye bilerek basit tutuldu)
1. Son `window_days` günün verisi alınır; tarih tekrarları ortalanır, aykırı değerler budanır.
2. Doğrusal regresyon:  fiyat = a + b * gün   (scikit-learn LinearRegression)
   - b (eğim): günlük ortalama fiyat değişimi (TL/gün)
   - Gün, ilk tarihten itibaren geçen gün sayısıdır; eksik günler sorun olmaz.
3. Tahmin:  ŷ(son_gün + 7) = a + b * (son_gün + 7)
4. Trend:   haftalık değişim = b * 7 / güncel seviye * 100
            > +%2 ise "up", < -%2 ise "down", arası "stable"
5. Tahmin aralığı: ŷ ± 1,96 * (artıkların standart sapması)
6. Geri test (backtest): Geçmişte farklı günlerde "o güne kadarki veriyle" tahmin yapılıp
   gerçekleşen fiyatla karşılaştırılır. Model hatası (MAPE), hiçbir şey yapmayan
   "naif tahmin"le (yarın da bugünkü fiyat olur) kıyaslanır.
7. Güven skoru (0-1) = doğruluk × veri yeterliliği
   - doğruluk       = 1 - MAPE / %15   (geri test hatası %15 ve üstüyse 0)
   - veri yeterliği = 0,5 + 0,5 × (gözlem sayısı / pencere gün sayısı)
"""
from dataclasses import dataclass, field
from datetime import date, timedelta
from statistics import median

import numpy as np
from sklearn.linear_model import LinearRegression

UP, DOWN, STABLE = "up", "down", "stable"


class InsufficientDataError(ValueError):
    """Güvenilir bir tahmin için yeterli geçmiş veri yok."""


@dataclass(frozen=True)
class PricePoint:
    day: date
    price: float


@dataclass(frozen=True)
class Forecast:
    current_price: float          # son 7 gözlemin ortalaması ("bugünkü seviye")
    predicted_price: float        # hedef gündeki tahmin
    target_date: date
    horizon_days: int
    slope_per_day: float          # TL / gün
    weekly_change_pct: float      # trend gücü (% / hafta)
    trend: str                    # up / down / stable
    lower: float                  # %95 tahmin aralığı alt sınırı
    upper: float                  # %95 tahmin aralığı üst sınırı
    r2: float                     # doğrusal uyum (0-1); düz seride düşük olabilir, tek başına güven değildir
    residual_std: float
    confidence: float             # 0-1
    n_points: int
    backtest_mape: float = None   # modelin geri test hatası (oran, 0.05 = %5)
    naive_mape: float = None      # naif tahminin geri test hatası
    history: tuple = field(default=(), repr=False)

    @property
    def expected_change_pct(self):
        return (self.predicted_price - self.current_price) / self.current_price * 100

    @property
    def beats_naive(self):
        if self.backtest_mape is None or self.naive_mape is None:
            return None
        return self.backtest_mape <= self.naive_mape


# --- 1. Veri hazırlama ------------------------------------------------------------------------

def prepare_series(points, window_days):
    """Sıralar, aynı günü ortalar, son `window_days` günü alır ve aykırı değerleri budar."""
    by_day = {}
    for point in points:
        if point.price is None or point.price <= 0:
            continue
        by_day.setdefault(point.day, []).append(float(point.price))
    if not by_day:
        return []

    last_day = max(by_day)
    start = last_day - timedelta(days=window_days - 1)
    series = [PricePoint(day, sum(values) / len(values))
              for day, values in sorted(by_day.items()) if day >= start]
    return clip_outliers(series)


def clip_outliers(series, k=3.0):
    """Medyandan k × MAD'den fazla sapan değerleri sınıra çeker (veri giriş hatalarına karşı).

    MAD (medyan mutlak sapma) ortalama/standart sapmaya göre aykırı değerlerden çok daha az etkilenir.
    """
    if len(series) < 5:
        return series
    prices = [p.price for p in series]
    center = median(prices)
    mad = median(abs(p - center) for p in prices) * 1.4826  # normal dağılımda std'ye denk gelir
    if mad == 0:
        return series
    low, high = center - k * mad, center + k * mad
    return [PricePoint(p.day, min(max(p.price, low), high)) for p in series]


# --- 2. Doğrusal regresyon --------------------------------------------------------------------

def fit_linear(series):
    """Fiyatı güne göre doğrusal modeller. (eğim, kesişim, R², artık std) döndürür."""
    first = series[0].day
    x = np.array([[(p.day - first).days] for p in series], dtype=float)
    y = np.array([p.price for p in series], dtype=float)

    model = LinearRegression().fit(x, y)
    fitted = model.predict(x)
    residuals = y - fitted
    ss_res = float(np.sum(residuals ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    dof = max(len(y) - 2, 1)  # 2 parametre (a, b) tahmin edildi
    residual_std = (ss_res / dof) ** 0.5
    return float(model.coef_[0]), float(model.intercept_), max(r2, 0.0), residual_std


def _predict_at(series, slope, intercept, target):
    return intercept + slope * (target - series[0].day).days


def classify_trend(weekly_change_pct, threshold_pct):
    if weekly_change_pct > threshold_pct:
        return UP
    if weekly_change_pct < -threshold_pct:
        return DOWN
    return STABLE


# --- 3. Geri test -----------------------------------------------------------------------------

def backtest(series, horizon_days, window_days, min_train=10, max_origins=10):
    """Geçmişteki birkaç başlangıç noktasında "geleceği bilmeden" tahmin yapıp hatayı ölçer.

    (model_mape, naive_mape) döndürür; yeterli test noktası yoksa (None, None).
    """
    by_day = {p.day: p.price for p in series}
    model_errors, naive_errors = [], []

    origins = [i for i in range(min_train - 1, len(series))
               if series[i].day + timedelta(days=horizon_days) in by_day]
    for i in origins[-max_origins:]:
        train = [p for p in series[: i + 1] if p.day > series[i].day - timedelta(days=window_days)]
        if len(train) < min_train:
            continue
        target = series[i].day + timedelta(days=horizon_days)
        actual = by_day[target]
        slope, intercept, _, _ = fit_linear(train)
        predicted = _predict_at(train, slope, intercept, target)
        model_errors.append(abs(predicted - actual) / actual)
        naive_errors.append(abs(train[-1].price - actual) / actual)  # "fiyat değişmez" varsayımı

    if not model_errors:
        return None, None
    return float(np.mean(model_errors)), float(np.mean(naive_errors))


def confidence_score(backtest_mape, residual_std, current_price, n_points, window_days, max_error=0.15):
    error = backtest_mape if backtest_mape is not None else residual_std / current_price
    accuracy = min(max(1 - error / max_error, 0.0), 1.0)
    data_factor = 0.5 + 0.5 * min(n_points / window_days, 1.0)
    return round(accuracy * data_factor, 2)


# --- 4. Tahmin --------------------------------------------------------------------------------

def forecast(points, horizon_days=7, window_days=30, min_points=14, stable_threshold_pct=2.0):
    """Ana giriş noktası. Yeterli veri yoksa InsufficientDataError fırlatır."""
    series = prepare_series(points, window_days)
    if len(series) < min_points:
        raise InsufficientDataError(
            f"Tahmin için en az {min_points} günlük veri gerekir; {len(series)} gün var.")

    slope, intercept, r2, residual_std = fit_linear(series)
    target = series[-1].day + timedelta(days=horizon_days)
    predicted = max(_predict_at(series, slope, intercept, target), 0.01)  # fiyat negatif olamaz

    recent = [p.price for p in series[-7:]]
    current = sum(recent) / len(recent)
    weekly_change_pct = slope * 7 / current * 100

    model_mape, naive_mape = backtest(series, horizon_days, window_days)
    margin = 1.96 * residual_std  # ~%95 aralık (basitleştirme: ufuk uzadıkça artan belirsizlik ihmal edildi)

    return Forecast(
        current_price=round(current, 2),
        predicted_price=round(predicted, 2),
        target_date=target,
        horizon_days=horizon_days,
        slope_per_day=round(slope, 4),
        weekly_change_pct=round(weekly_change_pct, 2),
        trend=classify_trend(weekly_change_pct, stable_threshold_pct),
        lower=round(max(predicted - margin, 0.01), 2),
        upper=round(predicted + margin, 2),
        r2=round(r2, 3),
        residual_std=round(residual_std, 3),
        confidence=confidence_score(model_mape, residual_std, current, len(series), window_days),
        n_points=len(series),
        backtest_mape=None if model_mape is None else round(model_mape, 4),
        naive_mape=None if naive_mape is None else round(naive_mape, 4),
        history=tuple(series),
    )
