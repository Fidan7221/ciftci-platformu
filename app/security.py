"""Uygulama genelindeki güvenlik katmanı (Hafta 11).

1) GÜVENLİK BAŞLIKLARI (her yanıta eklenir)
   - Content-Security-Policy (CSP): Tarayıcıya "yalnızca şu kaynaklardan betik çalıştır" der.
     Bir saldırgan sayfaya <script> enjekte etmeyi başarsa bile (XSS), betik nonce taşımadığı
     için tarayıcı onu ÇALIŞTIRMAZ. Satır içi olay işleyicileri (onclick=...) de engellenir.
   - X-Frame-Options / frame-ancestors: Sitemiz başka bir sitede <iframe> içine alınamaz (clickjacking).
   - X-Content-Type-Options: nosniff: Tarayıcı dosya türünü tahmin etmeye çalışmaz
     (ör. resim diye yüklenmiş bir dosyayı betik olarak çalıştırmaz).
   - Referrer-Policy, Permissions-Policy: Gereksiz bilgi sızıntısını ve izinleri kapatır.
   - Strict-Transport-Security (yalnızca üretimde): Tarayıcı siteye hep HTTPS ile bağlanır.

2) NONCE: Her istekte rastgele üretilen tek kullanımlık değer. Kendi <script> etiketlerimize
   nonce="{{ csp_nonce() }}" yazarız; CSP yalnızca bu nonce'u taşıyan betiklere izin verir.

3) SORGU SAYACI (geliştirme/test): Her isteğin kaç SQL sorgusu çalıştırdığını sayar ve
   X-Query-Count başlığına yazar. N+1 sorununu yakalamak için kullanılır.
"""
import secrets

from flask import g, has_request_context
from sqlalchemy import event
from sqlalchemy.engine import Engine

CDN = "https://cdn.jsdelivr.net"


def build_csp(nonce):
    return "; ".join([
        "default-src 'self'",
        f"script-src 'self' 'nonce-{nonce}' {CDN}",
        f"style-src 'self' 'unsafe-inline' {CDN}",   # Bootstrap'in style="" kullanımları için
        f"font-src 'self' {CDN}",                       # Bootstrap Icons yazı tipi
        "img-src 'self' data: blob:",                   # blob: görsel önizlemesi için
        "connect-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",                           # formlar yalnızca kendi sitemize gönderilir
        "frame-ancestors 'none'",
    ])


def _count_queries(conn, cursor, statement, parameters, context, executemany):
    if has_request_context():
        g.query_count = g.get("query_count", 0) + 1


def init_security(app):
    # Sorgu sayacı tüm motorlara bağlanır ama yalnızca istek sırasında sayar
    if not event.contains(Engine, "before_cursor_execute", _count_queries):
        event.listen(Engine, "before_cursor_execute", _count_queries)

    @app.before_request
    def create_nonce():
        g.csp_nonce = secrets.token_urlsafe(16)
        g.query_count = 0

    @app.context_processor
    def inject_nonce():
        return {"csp_nonce": lambda: g.get("csp_nonce", "")}

    @app.after_request
    def security_headers(response):
        headers = response.headers
        headers.setdefault("Content-Security-Policy", build_csp(g.get("csp_nonce", "")))
        headers.setdefault("X-Content-Type-Options", "nosniff")
        headers.setdefault("X-Frame-Options", "DENY")
        headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if app.config.get("SESSION_COOKIE_SECURE"):
            headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        if app.config.get("QUERY_COUNT_HEADER"):
            headers["X-Query-Count"] = str(g.get("query_count", 0))
        return response
