"""Tüm harici HTTP API'lerinin ortak istemcisi (Hafta 9).

Sağladıkları:
- ZAMAN AŞIMI: Her istek (bağlantı, okuma) sınırlıdır. Timeout verilmeyen bir
  requests çağrısı, karşı taraf yanıt vermezse sonsuza kadar bekleyebilir.
- YENİDEN DENEME: Geçici hatalarda (bağlantı hatası, zaman aşımı, 5xx) üstel
  bekleme (exponential backoff) ile sınırlı sayıda tekrar dener. 4xx hatalar
  tekrar denenmez; isteğin kendisi hatalıdır.
- HIZ SINIRI: İstemci tarafı sınırlayıcı (RateLimiter) servise kotadan fazla
  istek atılmasını önler; servisten 429 gelirse Retry-After okunur.
- GÜVENLİK: API anahtarı URL'ye değil başlığa (header) konur ve asla loglanmaz.
"""
import logging
import time

import requests

from app.integrations.errors import ExternalServiceError, ExternalTimeout, RateLimitExceeded

logger = logging.getLogger(__name__)

RETRYABLE_STATUS = {500, 502, 503, 504}


class ApiClient:
    def __init__(self, base_url, api_key=None, *, name="api", timeout=10.0, connect_timeout=3.05,
                 max_retries=2, backoff=0.5, rate_limiter=None, session=None, sleep=time.sleep):
        self.base_url = (base_url or "").rstrip("/")
        self._api_key = api_key           # "_" ile başlar: dışarıda kullanılmaması gereken alan
        self.name = name
        self.timeout = (connect_timeout, timeout)  # (bağlantı süresi, okuma süresi)
        self.max_retries = max_retries
        self.backoff = backoff
        self.rate_limiter = rate_limiter
        self.session = session or requests.Session()
        self.sleep = sleep                # Testlerde gerçekten beklememek için değiştirilebilir

    def __repr__(self):
        # Nesne yanlışlıkla loglansa bile anahtar görünmesin
        return f"<ApiClient {self.name} {self.base_url} key={'***' if self._api_key else 'yok'}>"

    def _headers(self, extra=None):
        headers = {"Accept": "application/json", "User-Agent": "TarladanSofraya/0.9 (+egitim projesi)"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        headers.update(extra or {})
        return headers

    @staticmethod
    def _retry_after(response):
        value = response.headers.get("Retry-After")
        try:
            return int(value) if value is not None else None
        except ValueError:
            return None

    def request(self, method, path, *, params=None, json=None, data=None, headers=None):
        """İsteği gönderir ve JSON gövdesini sözlük olarak döndürür; hata olursa IntegrationError fırlatır."""
        if self.rate_limiter is not None and not self.rate_limiter.hit(self.name):
            raise RateLimitExceeded(
                f"{self.name}: istemci tarafı hız sınırı doldu.", service=self.name,
                retry_after=self.rate_limiter.retry_after(self.name))

        url = f"{self.base_url}/{path.lstrip('/')}"
        last_error = None

        for attempt in range(self.max_retries + 1):
            started = time.monotonic()
            try:
                response = self.session.request(method, url, params=params, json=json, data=data,
                                                headers=self._headers(headers), timeout=self.timeout)
            except requests.Timeout:
                last_error = ExternalTimeout(f"{self.name} zaman aşımına uğradı.", service=self.name)
            except requests.ConnectionError:
                last_error = ExternalServiceError(f"{self.name} servisine bağlanılamadı.", service=self.name)
            else:
                elapsed_ms = (time.monotonic() - started) * 1000
                # Not: başlıklar (anahtar içerir) ve gövde (kart bilgisi içerebilir) loglanmaz
                logger.info("%s %s %s -> %s (%.0f ms)", self.name, method, url, response.status_code, elapsed_ms)

                if response.status_code == 429:
                    raise RateLimitExceeded(f"{self.name} hız sınırı aşıldı (429).", service=self.name,
                                            retry_after=self._retry_after(response))
                if response.status_code in RETRYABLE_STATUS:
                    last_error = ExternalServiceError(f"{self.name} geçici hata: {response.status_code}",
                                                      service=self.name, status_code=response.status_code)
                elif response.status_code >= 400:
                    raise ExternalServiceError(f"{self.name} isteği reddetti: {response.status_code}",
                                               service=self.name, status_code=response.status_code)
                else:
                    try:
                        return response.json()
                    except ValueError as error:
                        raise ExternalServiceError(f"{self.name} geçersiz JSON döndürdü.",
                                                   service=self.name) from error

            if attempt < self.max_retries:
                wait = self.backoff * (2 ** attempt)  # 0.5 s, 1 s, 2 s ... (üstel bekleme)
                logger.warning("%s: %s — %.1f sn sonra tekrar denenecek (%d/%d)",
                               self.name, last_error.message, wait, attempt + 1, self.max_retries)
                self.sleep(wait)

        raise last_error

    def get_json(self, path, params=None, headers=None):
        return self.request("GET", path, params=params, headers=headers)

    def post_json(self, path, payload, headers=None):
        return self.request("POST", path, json=payload, headers=headers)
