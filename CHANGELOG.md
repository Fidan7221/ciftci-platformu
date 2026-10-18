# Değişiklik Günlüğü

Sürüm numaraları [Semantic Versioning](https://semver.org/lang/tr/) kuralına uyar: `ANA.ARA.YAMA[-ön-sürüm]`.

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
