"""Hız sınırlama (rate limiting) — Hafta 9.

İki yerde kullanılır:
1. DIŞARI giden istekler: Fiyat API'sinin kotasını aşmamak için (http_client.ApiClient).
2. İÇERİ gelen istekler: Bir kullanıcının ödeme formunu dakikada yüzlerce kez
   denemesini (kart deneme saldırısı / "carding") engellemek için (@rate_limited).

Yöntem: kayan pencere (sliding window). Her anahtar için son `period` saniyedeki
istek zamanları tutulur; sayı `limit`e ulaştıysa yeni istek reddedilir.

Not: Sayaçlar sunucu belleğindedir. Tek süreçli geliştirme sunucusu için yeterlidir;
birden çok sunucu sürecinde ortak bir depo (ör. Redis + Flask-Limiter) gerekir.
"""
import math
import threading
import time
from collections import defaultdict, deque
from functools import wraps

from flask import abort, current_app, request
from flask_login import current_user


class RateLimiter:
    def __init__(self, limit, period, clock=time.monotonic):
        self.limit = limit
        self.period = period
        self.clock = clock              # Testlerde sahte saat verilebilir
        self._hits = defaultdict(deque)
        self._lock = threading.Lock()   # Aynı anda gelen iki istek sayacı bozmasın

    def _trim(self, key, now):
        window = self._hits[key]
        while window and window[0] <= now - self.period:
            window.popleft()
        return window

    def hit(self, key="global"):
        """İsteğe izin varsa sayar ve True döner; sınır dolduysa False."""
        now = self.clock()
        with self._lock:
            window = self._trim(key, now)
            if len(window) >= self.limit:
                return False
            window.append(now)
            return True

    def retry_after(self, key="global"):
        """Bir sonraki isteğe kaç saniye sonra izin verileceği."""
        now = self.clock()
        with self._lock:
            window = self._trim(key, now)
            if len(window) < self.limit:
                return 0
            return max(1, math.ceil(window[0] + self.period - now))

    def reset(self, key=None):
        with self._lock:
            if key is None:
                self._hits.clear()
            else:
                self._hits.pop(key, None)


def get_limiter(name, limit, period):
    """Uygulamaya özel sınırlayıcıyı döndürür (her test yeni uygulama = temiz sayaç)."""
    limiters = current_app.extensions.setdefault("rate_limiters", {})
    if name not in limiters:
        limiters[name] = RateLimiter(limit, period)
    return limiters[name]


def rate_limited(name, limit_config_key, period):
    """Rota dekoratörü: kullanıcı başına (giriş yoksa IP başına) istek sınırı.

    Yalnızca POST istekleri sayılır; sayfayı görüntülemek serbesttir.
    Sınır aşılırsa 429 Too Many Requests + Retry-After başlığı döner.
    """

    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if request.method == "POST":
                limiter = get_limiter(name, current_app.config[limit_config_key], period)
                key = f"user:{current_user.id}" if current_user.is_authenticated else f"ip:{request.remote_addr}"
                if not limiter.hit(key):
                    current_app.logger.warning("Hız sınırı aşıldı: %s %s", name, key)
                    abort(429, description=limiter.retry_after(key))
            return view(*args, **kwargs)

        return wrapped

    return decorator
