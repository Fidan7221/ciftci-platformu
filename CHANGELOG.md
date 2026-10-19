# Değişiklik Günlüğü

Sürüm numaraları [Semantic Versioning](https://semver.org/lang/tr/) kuralına uyar: `ANA.ARA.YAMA[-ön-sürüm]`.

## [0.13.0] — 2026-10-19 · Dağıtım, paketleme ve masaüstü uygulaması (Final)

### Eklendi
- Masaüstü uygulaması: `desktop_app.py`, `desktop/launcher.py` (veri klasörü, tek kopya kontrolü, gizli anahtar
  üretimi, boş port, yalnızca 127.0.0.1, waitress sunucusu, düzgün kapanış), `desktop/control_window.py`
  (tkinter kontrol penceresi), isteğe bağlı pywebview penceresi.
- `build_exe.py`: PyInstaller ile .exe (klasör / tek dosya, konsollu hata ayıklama, masaüstü kısayolu);
  kullanıcı yüklemeleri ve `.env` pakete girmez. `requirements-desktop.txt`.
- Uygulama ikonu (`desktop/make_icon.py`, `icon.ico`, `icon.png`, `favicon.png`).
- `DesktopConfig` ve `create_app(config_name, overrides, instance_path)`; bilinmeyen ortam adı hata verir.
- Log: dönen dosyalar (`logs/uygulama.log`, 1 MB × 5), istek kimliği (`X-Request-ID`), istek logu (üretim);
  500 sayfasında hata kodu.
- `GET /saglik` sağlık kontrolü; `GET /medya/<dosya>` (yüklemeler statik dosyalardan ayrıldı).
- `flask kurulum [--demo] [--sifirla] [--evet]`: veri tabanını tek komutla hazırlar (`app/bootstrap.py`).
- Ön yüz kütüphanelerinin yerel kopyası: `scripts/download_assets.py`, `app/assets.py` (`vendor_url()`).
- `docs/FINAL_RAPORU.md`, `docs/FINAL_SOZLU_HAZIRLIK.md`, `docs/MASAUSTU_KILAVUZU.md`.
- `tests/test_deployment.py` (33 test, gerçek sunucuyla uçtan uca başlatıcı testi dahil) — toplam 353.

### Değişti
- `requirements.txt`: `waitress`. `.gitignore`: `logs/`, `build/`, `dist/`, `*.spec`.
- Ürün görselleri `/static/uploads/` yerine `/medya/` adresinden verilir (dosyaların yeri değişmedi).
- `base.html`: Bootstrap / Chart.js adresleri `vendor_url()` ile (yerelde varsa yerel, yoksa CDN).

## [0.12.0] — 2026-10-19 · Gelişmiş arama, raporlama ve dışa aktarma

### Eklendi
- Pazar yerinde çoklu filtre: kategori (alt kategorilerle), il/ilçe, fiyat aralığı, organik, doğrulanmış üretici;
  sıralama: en ilgili, en yeni, fiyat artan/azalan, en çok değerlendirilen, en yüksek puan. Seçili filtre etiketleri.
- Türkçe duyarsız metin araması: SQLite'a `tr_fold()` fonksiyonu (`app/utils/text.py`, `app/extensions.py`);
  ilan, ürün, açıklama, çiftlik, bölge ve kategoride; çok kelimede her kelime eşleşmeli.
- `MarketFilter` ve `RegionIndex` (`app/utils/market_filter.py`), `search_service`.
- Üretici "İlanlarım" sayfasında arama ve sıralama.
- Raporlar (`/raporlar/`): `report_service`, `ReportRepository` (tek sorgu), `app/reports/` (dönem, hesaplama,
  CSV, PDF). Üretici kendi, yönetici tüm platform verisini görür.
- CSV (UTF-8 BOM, `;`, formül enjeksiyonu koruması) ve PDF (ReportLab, DejaVu Sans gömülü, grafik) dışa aktarma.
- `orders.created_at` indeksi (migration gerekir), `REPORT_MAX_ROWS`, `REPORT_EXPORTS_PER_MIN` ayarları.
- `seed-demo`: ikinci demo müşteri ve son 45 güne yayılmış demo siparişleri (gerçek sipariş akışıyla).
- `docs/ARAMA_VE_RAPORLAMA.md`, `tests/test_search.py` (48), `tests/test_reports.py` (48) — toplam 320.

### Değişti
- `rate_limited` artık `methods` parametresi alır (indirmeler GET olduğu için).
- `requirements.txt`: `reportlab`.
- Pazar sayfası yeni düzen: solda filtre paneli (mobilde katlanır), sağda arama ve sonuçlar.

## [0.11.0] — 2026-10-19 · Güvenlik, ince yetkilendirme ve performans

### Eklendi
- `app/security.py`: istek başına nonce'lu Content-Security-Policy, `X-Frame-Options`, `X-Content-Type-Options`,
  `Referrer-Policy`, `Permissions-Policy`, üretimde HSTS; geliştirme/testte `X-Query-Count` sorgu sayacı.
- Hesap kilitleme (15 dk'da 5 hatalı giriş), IP başına giriş/kayıt sınırı, sepete ekleme sınırı (`429`).
- Zamanlama saldırısına karşı: olmayan e-postada da sahte parola hash'i doğrulanır.
- Veritabanı indeksleri: `listings(status, created_at)`, `orders(customer_id, created_at)`,
  `market_prices(category_id, price_date)`, `price_predictions(product_id, model_name, target_date)`,
  `products.category_id`, `categories.parent_id`, `users.role_id`, `cart_items.listing_id`, `order_items.listing_id`,
  `reviews.customer_id` (migration gerekir).
- `static/js/app.js` (onay pencereleri ve geri bağlantısı), `docs/GUVENLIK_DENETIMI.md`.
- `docs/ER_DIYAGRAMI.md` + `docs/er_diyagrami.png`: 14 tablonun güncel ER diyagramı (Mermaid).
- `tests/test_security.py` (41 test) — toplam 224.

### Değişti
- Şablonlardaki satır içi `onsubmit` / `javascript:` kaldırıldı (`data-confirm`, `data-back`); satır içi betiklere nonce eklendi.
- İlan formundaki JS verisi `tojson` ile aktarılıyor.
- Arama sorgularında `%` ve `_` joker karakterleri kaçırılıyor (`contains_pattern`).
- N+1 düzeltmeleri: pazar, sipariş listeleri, sepet, yönetici kategorileri (`GROUP BY` sayımı), fiyat tablosu
  (önceki gün ortalamaları ve tahminler tek sorguda), oturum kullanıcısı rol/profil ile birlikte yükleniyor.
- `session_protection = "strong"`; üretimde varsayılan veya 32 karakterden kısa `SECRET_KEY` ile uygulama başlamaz.

## [0.10.0] — 2026-10-19 · Yapay zekâ: fiyat tahmini ve trend analizi

### Eklendi
- `app/ai/trend_model.py`: doğrusal regresyon (scikit-learn) ile 7 günlük hal fiyatı tahmini, trend (artış/düşüş/dengeli),
  %95 tahmin aralığı, aykırı değer budama, walk-forward geri test (naif tahminle kıyas), güven skoru.
- `app/ai/sell_advisor.py`: satış zamanı önerisi (bekle / şimdi sat / dengeli / düşük güven) ve fiyat bandı (taban-önerilen-tavan).
- `prediction_service`: kategori serisinden tahmin, `price_predictions` tablosuna kayıt (upsert), panel kartları.
- Arayüz: üretici panelinde AI kartları ve grafik, ilan formunda "Önerilen fiyatı kullan", müşteri panelinde
  piyasa trendleri, fiyat tablosunda "7 gün tahmini" sütunu, `/fiyatlar/<ürün>` model özeti sayfası, ilan detayında trend kartı.
- Chart.js grafik bileşeni (`static/js/price_chart.js`), `docs/MODEL_KARTI.md`, `flask predict-prices`.
- `tests/test_ai.py` (32 test) — toplam 183.

### Değişti
- `price_predictions` tablosuna `current_price`, `lower_price`, `upper_price`, `suggested_min_price`, `suggested_price`,
  `suggested_max_price`, `action`, `backtest_mape` eklendi (migration).
- `requirements.txt`: `numpy`, `scikit-learn`. `seed-demo` artık 60 günlük fiyat ve tahmin üretir.

## [0.9.0] — 2026-10-19 · Harici API entegrasyonu

### Eklendi
- `app/integrations/`: ortak HTTP istemcisi (zaman aşımı, üstel beklemeli yeniden deneme, 429/Retry-After,
  istemci tarafı hız sınırı, anahtarın loglanmaması), hal fiyatı sağlayıcıları (sahte + HTTP adaptörü),
  ödeme sağlayıcıları (test kartlı sahte sağlayıcı + HMAC imzalı HTTP adaptörü, idempotency anahtarı).
- Ödeme sayfası (`/odeme/siparis/<id>`): Luhn ve son kullanma kontrolü, kart numarası saklanmaz (yalnızca son 4 hane),
  kullanıcı başına deneme sınırı (429).
- Ödenmiş siparişin iptalinde otomatik iade; iade başarısızsa sipariş iptal edilmez.
- Hal fiyatları sayfası (`/fiyatlar`), yönetici için "şimdi güncelle" düğmesi; ilan detayında ve ilan formunda
  hal ortalaması karşılaştırması.
- Komutlar: `flask fetch-prices`, `flask cancel-unpaid`. `seed-demo` artık 30 günlük fiyat da ekler.
- `.env.example` harici API değişkenleriyle güncellendi.
- Testler: `test_integrations.py` (23), `test_payments.py` (21), `test_prices.py` (12) — toplam 151.

### Değişti
- Sipariş "ödendi" durumuna artık üretici elle geçiremez; ödeme sağlayıcısı (veya yönetici, havale için) geçirir.
- Tek üreticili siparişte sepet onayından sonra doğrudan ödeme sayfasına gidilir.
- `payments` tablosuna `idempotency_key`, `attempt_count`, `card_last4`, `refund_ref`, `refunded_at` eklendi (migration).

## [0.8.0-vize] — 2026-10-19 · Vize ara sürümü

### Hafta 8 — Entegrasyon ve düzeltmeler
- **Düzeltme:** Tarih/saatler ekranda UTC görünüyordu; artık Türkiye saatiyle (UTC+3) gösteriliyor.
- **Düzeltme:** Süresi dolan CSRF anahtarı ham "400 Bad Request" sayfası yerine uyarı mesajıyla forma geri döndürüyor (yalnızca kendi sitemize).
- **Düzeltme:** Hafta 7 menüsünde üretici profil bağlantısı kaybolmuştu; kullanıcı menüsüne taşındı.
- **Eklendi:** Rol bazlı menü, aktif sayfa vurgusu, kullanıcı açılır menüsü, alt bilgide sürüm numarası.
- **Eklendi:** Müşteri/yönetici "Hesap bilgilerim" sayfası (varsayılan teslimat adresi).
- **Eklendi:** Yönetici paneli istatistikleri ve tüm siparişler listesi.
- **Eklendi:** Üretici panelinde "ilgilenilecek sipariş" ve "aktif ilan" sayıları; müşteri panelinde son siparişler.
- **Eklendi:** 500 hata sayfası (yarım kalan işlem `rollback` edilir), oturum çerezi güvenlik ayarları.
- **Eklendi:** `flask seed-demo` komutu, `test_integration.py` (14 test), README ve vize belgeleri.

### Hafta 7 — İlan, sepet, sipariş
- İlan yönetimi, pazar vitrini, sepet, sipariş oluşturma (tek transaction), fiyat dondurma.
- Koşullu UPDATE ile yarış durumuna (race condition) dayanıklı stok düşürme.
- Sipariş durum makinesi (ödeme bekleniyor → ödendi → kargoda → teslim edildi / iptal), iptalde stok iadesi.

### Hafta 6 — Üretici ve ürün kaydı
- Üretici profili, ürün CRUD'u, görsel yükleme (imza kontrolü), kategori yönetimi, ürün stoğu.

### Hafta 5 — Kullanıcı yönetimi
- Kayıt/giriş, scrypt ile parola hashleme, `@role_required`, CSRF, açık yönlendirme koruması.

### Hafta 3-4 — Mimari ve veri tabanı
- Katmanlı proje iskeleti, uygulama fabrikası, 14 tablolu veri modeli, Flask-Migrate.
