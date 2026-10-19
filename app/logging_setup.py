"""Log yapılandırması (Hafta 13).

- Her isteğe kısa bir kimlik (request id) verilir. Bu kimlik yanıt başlığında (X-Request-ID), 500 hata
  sayfasında ("Hata kodu") ve o isteğe ait TÜM log satırlarında görünür. Kullanıcı hata kodunu bildirince
  log dosyasında aranıp ilgili satırlar bulunur.
- Üretimde (ve masaüstü uygulamasında) loglar dönen dosyalara yazılır: LOG_DIR/uygulama.log,
  her biri en fazla 1 MB, en fazla 5 eski dosya. Disk dolmaz.
- Loglara parola, kart numarası, oturum çerezi gibi gizli bilgiler YAZILMAZ; yalnızca yöntem, yol, durum
  kodu ve süre yazılır (sorgu parametreleri de yazılmaz: arama metni kişisel bilgi içerebilir).
"""
import logging
import os
import re
import time
import uuid
from logging.handlers import RotatingFileHandler

from flask import g, has_request_context, request

LOG_FORMAT = "%(asctime)s %(levelname)-7s [%(request_id)s] %(name)s: %(message)s"
LOG_FILE_NAME = "uygulama.log"
MAX_BYTES = 1_000_000
BACKUP_COUNT = 5
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9-]{8,64}$")
_HANDLER_MARK = "_ciftci_handler"


class RequestIdFilter(logging.Filter):
    """Log kaydına istek kimliğini ekler (istek dışında "-")."""

    def filter(self, record):
        record.request_id = g.get("request_id", "-") if has_request_context() else "-"
        return True


_REQUEST_FILTER = RequestIdFilter()   # tek örnek: addFilter aynı filtreyi ikinci kez eklemez


def new_request_id(incoming=None):
    """Ters vekil (Nginx) bir kimlik gönderdiyse ve biçimi güvenliyse onu kullan; yoksa yenisini üret.
    Biçim kontrolü, log dosyasına satır sonu vb. enjekte edilmesini (log injection) önler."""
    if incoming and _REQUEST_ID_PATTERN.match(incoming):
        return incoming
    return uuid.uuid4().hex[:12]


def _remove_our_handlers(logger):
    # create_app() testlerde defalarca çağrılır; aynı dosyaya ikinci kez yazan handler eklenmesin
    for handler in list(logger.handlers):
        if getattr(handler, _HANDLER_MARK, False):
            logger.removeHandler(handler)
            handler.close()


def configure_logging(app):
    level = getattr(logging, str(app.config.get("LOG_LEVEL", "INFO")).upper(), logging.INFO)
    app.logger.setLevel(level)
    _remove_our_handlers(app.logger)

    formatter = logging.Formatter(LOG_FORMAT)
    request_filter = _REQUEST_FILTER
    for handler in app.logger.handlers:          # Flask'ın varsayılan (konsol) handler'ı da kimliği yazsın
        handler.addFilter(request_filter)
        handler.setFormatter(formatter)

    if app.config.get("LOG_TO_FILE"):
        log_dir = app.config["LOG_DIR"]
        os.makedirs(log_dir, exist_ok=True)
        file_handler = RotatingFileHandler(os.path.join(log_dir, LOG_FILE_NAME), maxBytes=MAX_BYTES,
                                           backupCount=BACKUP_COUNT, encoding="utf-8", delay=True)
        file_handler.setFormatter(formatter)
        file_handler.addFilter(request_filter)
        file_handler.setLevel(level)
        setattr(file_handler, _HANDLER_MARK, True)
        app.logger.addHandler(file_handler)

    @app.before_request
    def _assign_request_id():
        g.request_id = new_request_id(request.headers.get("X-Request-ID"))
        g.request_started = time.perf_counter()

    @app.after_request
    def _log_request(response):
        response.headers.setdefault("X-Request-ID", g.get("request_id", "-"))
        if app.config.get("LOG_REQUESTS") and not request.path.startswith("/static/"):
            elapsed_ms = (time.perf_counter() - g.get("request_started", time.perf_counter())) * 1000
            app.logger.info("%s %s -> %s (%.0f ms)", request.method, request.path, response.status_code, elapsed_ms)
        return response
