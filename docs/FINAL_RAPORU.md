# P11 — Final Raporu: Tarladan Sofraya

**Çiftçi Doğrudan Satış ve Fiyat Takip Platformu**
Bingöl Üniversitesi · Bilgisayar Programcılığı · Dönem Projesi · Sürüm `v0.13.0`

| | |
|---|---|
| Öğrenci | [Ad Soyad] — [Öğrenci No] |
| Ders / Danışman | [Ders adı] — [Öğretim elemanı] |
| Depo | [GitHub bağlantısı] |
| Teslim | [Tarih] |

## 1. Özet

Tarladan Sofraya, üreticilerin ürünlerini aracısız satabildiği, müşterilerin doğrudan üreticiden alışveriş
yaptığı ve herkesin hal fiyatlarını takip edebildiği bir web uygulamasıdır. Üretici ürün ve ilan açar,
müşteri sepet ve siparişle satın alır, yönetici platformu izler. Hal fiyatları harici bir servisten çekilir;
yapay zekâ modülü 7 günlük fiyat tahmini ve satış önerisi üretir. Raporlar CSV/PDF olarak indirilebilir.
Proje sunucuda çalışabildiği gibi, çift tıklayınca açılan bir **masaüstü uygulaması** olarak da paketlenir.

## 2. Teknoloji yığını ve seçim gerekçeleri

| Katman | Seçim | Neden |
|---|---|---|
| Dil / çatı | Python 3.11+, Flask 3 | Öğrenmesi kolay, küçük çekirdek; Blueprint ile modüler yapı |
| Veri | SQLite + SQLAlchemy 2, Flask-Migrate (Alembic) | Kurulum gerektirmez; ORM ile SQL injection'a karşı parametreli sorgular; şema değişikliği migration ile |
| Arayüz | Jinja2 + Bootstrap 5, Chart.js | Sunucu taraflı şablon: ayrı bir ön yüz projesi gerekmez; mobil uyumlu |
| Güvenlik | Flask-Login, Flask-WTF (CSRF), Werkzeug hash | Oturum, form doğrulama ve parola hash'leme hazır ve denenmiş |
| Yapay zekâ | NumPy, scikit-learn (doğrusal regresyon) | Açıklanabilir, az veriyle çalışan, hızlı model |
| Rapor | ReportLab (PDF), csv | Saf Python; Türkçe yazı tipi gömülebilir |
| Dağıtım | waitress, PyInstaller | Windows'ta çalışan üretim sunucusu; tek klasörde .exe |
| Test | pytest, pytest-flask | 353 otomatik test |

## 3. Mimari

Katmanlı mimari — her katman yalnızca bir alttakini çağırır:

```
Sunum        routes/ (11 Blueprint) · forms/ · templates/ (34 şablon) · static/
   │  HTTP isteğini alır, formu doğrular, servisi çağırır, şablonu çizer. İş kuralı içermez.
İş mantığı   services/ (auth, producer, category, listing, cart, order, payment, price,
   │          prediction, search, report)  ·  ai/ · reports/ · integrations/
   │  Kurallar burada: stok, durum geçişleri, yetki kapsamı, ciro tanımı...
Veri erişimi repositories/  — tüm sorgular, atomik stok güncellemeleri, eager loading
   │
Veri         models/ — 14 tablo (docs/ER_DIYAGRAMI.md)
```

Neden bu yapı? Aynı iş kuralı farklı yerlerden çağrılabiliyor (web sayfası, CLI komutu, masaüstü başlatıcısı,
testler). Örneğin `prepare_database()` hem `flask kurulum` komutunda hem `.exe`'nin ilk açılışında kullanılır.
Veri tabanından bağımsız modüller (`ai/`, `reports/`, `utils/market_filter.py`) milisaniyeler içinde test edilir.

## 4. Haftalara göre gelişim

| Hafta | Sürüm | Çıktı |
|---|---|---|
| 3-4 | 0.1 | Teknoloji seçimi, klasör yapısı, 14 tablolu ER şeması, modeller, seed verisi |
| 5 | 0.2 | Kayıt / giriş / çıkış, parola hash'leme, `@role_required` (müşteri, üretici, yönetici) |
| 6 | 0.3 | Üretici profili, ürün CRUD, görsel yükleme (imza kontrolü), kategoriler, sayfalama |
| 7 | 0.4 | İlan, sepet, sipariş; transaction ve koşullu UPDATE ile stok; sipariş durum makinesi |
| 8 | 0.8 (vize) | Uçtan uca entegrasyon, 6 düzeltme, demo verisi, vize raporu |
| 9 | 0.9 | Harici API katmanı: hal fiyatları ve ödeme (timeout, yeniden deneme, 429, idempotency, HMAC) |
| 10 | 0.10 | Yapay zekâ: 7 günlük fiyat tahmini, güven skoru, satış önerisi, grafikler |
| 11 | 0.11 | Güvenlik denetimi (CSP, IDOR, brute force, timing), indeksler, N+1 düzeltmeleri |
| 12 | 0.12 | Gelişmiş filtre ve Türkçe duyarsız arama, satış raporları, CSV/PDF dışa aktarma |
| 13 | 0.13 | Üretim yapılandırması, log, sağlık kontrolü, tek komutla kurulum, masaüstü uygulaması (.exe) |

## 5. Öne çıkan teknik kararlar

**Stok tutarlılığı (Hafta 7).** Stok "oku → hesapla → yaz" yerine tek bir koşullu UPDATE ile düşer:
`UPDATE listings SET stock = stock - :q WHERE id = :id AND stock >= :q`. Etkilenen satır 0 ise stok yetmemiştir.
Aynı anda gelen iki sipariş son ürünü birlikte alamaz. Sipariş oluşturma tek transaction'dır; hata olursa
stoklar ve sepet eski hâline döner.

**Harici servisler (Hafta 9).** Tüm istekler ortak bir HTTP istemcisinden geçer: zaman aşımı, artan bekleme
ile yeniden deneme, 429 ve hız sınırı. Ödemede idempotency anahtarı aynı ödemenin iki kez çekilmesini önler.
Anahtarlar `.env`'den okunur; `USE_MOCK_APIS=true` iken internete çıkılmaz (ders, demo, test).

**Yapay zekâ (Hafta 10).** Son 30 günün hal fiyatına doğrusal regresyon; aykırı değer budama, %95 tahmin
aralığı, walk-forward geri test ile naif tahminle kıyaslanan güven skoru. Güven düşükse öneri verilmez.
Ayrıntı: `docs/MODEL_KARTI.md`.

**Güvenlik (Hafta 11).** CSRF jetonu, Jinja2 otomatik kaçış + nonce'lu CSP, parametreli sorgular ve LIKE joker
kaçışı, sahibine göre süzülen sorgularla IDOR koruması (başkasının kaydı → 404), hesap kilitleme ve IP hız
sınırları, zamanlama saldırısına karşı sahte hash, üretimde zayıf SECRET_KEY ile başlamama.
Ayrıntı: `docs/GUVENLIK_DENETIMI.md`.

**Performans (Hafta 11).** Sık sorgulanan sütunlara indeksler; `selectinload` / `joinedload` /
`contains_eager` ile N+1 giderildi. Geliştirme ortamında her yanıtın `X-Query-Count` başlığı vardır; testler
sorgu sayısının kayıt sayısıyla artmadığını doğrular.

**Arama ve raporlar (Hafta 12).** SQLite'a kaydedilen `tr_fold()` fonksiyonu ile Türkçe karakter ve büyük/küçük
harf duyarsız arama (`cilek` → "Çilek"). Raporlar tek sorgu + Python'da hesap; Türkiye saatine göre gün
sınırı; üretici yalnızca kendi verisini görür. CSV'de formül enjeksiyonu koruması, PDF'te gömülü Türkçe yazı tipi.
Ayrıntı: `docs/ARAMA_VE_RAPORLAMA.md`.

## 6. Dağıtım ve sistem entegrasyonu (Hafta 13)

| Konu | Çözüm |
|---|---|
| Ortamlar | `development`, `testing`, `production`, `desktop` (config.py). Bilinmeyen ortam adı hata verir. |
| Gizli bilgiler | Yalnızca ortam değişkeni / `.env` (git'e girmez). Üretim ve masaüstünde ≥ 32 karakter SECRET_KEY zorunlu. |
| Log | `logs/uygulama.log`, 1 MB × 5 dönen dosya; her satırda istek kimliği. Sorgu metni ve gizli bilgi loglanmaz. |
| Hata yönetimi | 500 sayfası iç ayrıntı göstermez, yalnızca "hata kodu" (istek kimliği) gösterir; aynı kod logda aranır. |
| Sağlık kontrolü | `GET /saglik` → `{"durum": "ok", "veritabani": "ok", "surum": ...}`; veri tabanı yoksa 503. |
| Kurulum | `flask kurulum [--demo] [--sifirla]`: tablolar, roller, kategoriler, isteğe bağlı demo; tekrar çalıştırmak güvenli. |
| Yüklemeler | `/medya/` adresinden; `UPLOAD_FOLDER` uygulama dosyalarından ayrı (paket salt-okunur olabilir). |
| Ön yüz | Bootstrap / Chart.js yerel kopyası (internetsiz çalışma), yoksa CDN. |
| Sunucu | `waitress` (Windows uyumlu üretim WSGI sunucusu); Flask'ın geliştirme sunucusu kullanılmaz. |
| Masaüstü | `desktop_app.py` + PyInstaller: veri klasörü, tek kopya, boş port, 127.0.0.1, kontrol penceresi, ikon, kısayol. Ayrıntı: `docs/MASAUSTU_KILAVUZU.md`. |

## 7. Test stratejisi

| Dosya | Test | Kapsam |
|---|---|---|
| `test_models.py` | 3 | Tablolar ve ilişkiler |
| `test_auth.py` | 13 | Kayıt, giriş, rol erişimi |
| `test_producer.py`, `test_categories.py` | 19 + 9 | Profil, ürün CRUD, görsel, kategoriler |
| `test_listings.py`, `test_cart.py`, `test_orders.py` | 14 + 11 + 12 | İlan, sepet, sipariş, transaction, durum makinesi |
| `test_integration.py` | 14 | Uçtan uca HTTP akışı, her rol için tüm sayfalar |
| `test_integrations.py`, `test_payments.py`, `test_prices.py` | 23 + 21 + 12 | Harici API katmanı, ödeme, iade, fiyat senkronu |
| `test_ai.py` | 32 | Tahmin algoritması, öneri kuralları, tahmin kaydı |
| `test_security.py` | 41 | CSP, XSS, SQLi, CSRF, IDOR, brute force, N+1, indeksler |
| `test_search.py`, `test_reports.py` | 48 + 48 | Arama, filtre, sıralama; raporlar, CSV, PDF |
| `test_deployment.py` | 33 | Log, sağlık, kurulum, masaüstü başlatıcısı (gerçek sunucu), derleme argümanları |
| **Toplam** | **353** | Harici servisler taklit edilir; testler internete çıkmaz. |

Test türleri: birim (saf fonksiyonlar), servis (veri tabanıyla), HTTP (test istemcisi), uçtan uca
(gerçek sunucu ve port: `test_desktop_launcher_end_to_end`), güvenlik ve performans (sorgu sayısı).

## 8. Yapay zekâ kullanımı

Kod, test ve belgelerin hazırlanmasında yapay zekâ (Claude) kullanıldı; her hafta `docs/AI_KULLANIM_GUNLUGU.md`
dosyasına işlendi. Yapay zekânın yaptığı hatalar ve nasıl yakalandıkları da aynı dosyada listelenir
(örneğin Hafta 12'de 13 arama testinin yanlış alarmı benim bilgisayarımda `pytest` ile bulundu). Teslim edilen
her parçayı okudum, çalıştırdım ve sözlüde açıklayabilecek düzeydeyim. [Kendi değerlendirmenizi ekleyin.]

## 9. Bilinen sınırlamalar

- SQLite tek yazıcı kilidi kullanır; çok kullanıcılı yoğun yükte PostgreSQL'e geçilmelidir (SQLAlchemy sayesinde
  büyük ölçüde yalnızca `DATABASE_URL` değişir; `tr_fold` fonksiyonu PostgreSQL'de ayrıca tanımlanmalıdır).
- Hız sınırı sayaçları bellektedir; birden çok sunucu işleminde Redis gibi ortak bir depo gerekir.
- `LIKE '%…%'` araması indeks kullanamaz; büyük veride FTS5 / pg_trgm gerekir.
- Masaüstü `.exe` imzasız olduğu için Windows SmartScreen uyarısı verir.
- Gerçek ödeme ve hal fiyatı servisleriyle yalnızca sahte (mock) modda denendi.
- Masaüstü veri tabanı `create_all` ile kurulur; yeni sürümde yeni sütun eklenirse veri klasörü sıfırlanmalı
  ya da migration desteği eklenmelidir.

## 10. Gelecek çalışmalar

E-posta ile sipariş bildirimi, üretici için stok uyarısı, mobil uygulama (aynı servis katmanı üzerine bir REST API),
PostgreSQL + Docker ile bulut dağıtımı, model için mevsimsellik (yıllık veri biriktikçe), kod imzalı kurulum paketi.

## 11. Çalıştırma

```bash
pip install -r requirements.txt
flask kurulum --demo            # veri tabanı + demo verisi (tek komut)
python run.py                   # http://127.0.0.1:5000   (parola: Demo12345)
pytest -v                       # 353 test
python build_exe.py --kisayol   # masaüstü uygulaması (requirements-desktop.txt gerekir)
```
