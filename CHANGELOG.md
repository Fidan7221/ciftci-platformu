# Değişiklik Günlüğü

Sürüm numaraları [Semantic Versioning](https://semver.org/lang/tr/) kuralına uyar: `ANA.ARA.YAMA[-ön-sürüm]`.

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
