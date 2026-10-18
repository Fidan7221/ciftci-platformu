"""Harici servis hataları (Hafta 9).

Servis katmanı yalnızca bu hata türlerini bilir; requests kütüphanesinin kendi
hata sınıfları (requests.Timeout vb.) integrations/ klasörünün dışına sızmaz.
Böylece yarın requests yerine başka bir HTTP kütüphanesi kullansak bile
servisler ve rotalar değişmez.
"""


class IntegrationError(Exception):
    """Tüm harici servis hatalarının atası."""

    def __init__(self, message, service=None, status_code=None):
        super().__init__(message)
        self.message = message
        self.service = service
        self.status_code = status_code


class ExternalTimeout(IntegrationError):
    """Servis belirlenen sürede yanıt vermedi. İşlemin karşı tarafta gerçekleşip
    gerçekleşmediği BİLİNMEZ; ödeme gibi işlemlerde aynı idempotency anahtarıyla tekrar denenmelidir."""


class ExternalServiceError(IntegrationError):
    """Bağlantı kurulamadı, 4xx/5xx yanıt geldi veya yanıt anlaşılamadı."""


class RateLimitExceeded(IntegrationError):
    """Hız sınırı aşıldı (ya bizim istemci tarafı sınırımız ya da servisin 429 yanıtı)."""

    def __init__(self, message, service=None, retry_after=None):
        super().__init__(message, service=service, status_code=429)
        self.retry_after = retry_after


class ConfigurationError(IntegrationError):
    """Gerçek servis seçili ama adres veya anahtar .env dosyasında tanımlı değil."""
