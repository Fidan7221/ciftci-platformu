# Tarladan Sofraya — Çiftçi Doğrudan Satış ve Fiyat Takip Platformu (P11)

Bingöl Üniversitesi Bilgisayar Programcılığı dönem projesi.
Çiftçilerin ürünlerini aracısız satabildiği, müşterilerin doğrudan üreticiden alışveriş yaptığı bir pazar yeri.

**Sürüm:** `v0.13.0` · **Teknoloji:** Python 3.11+, Flask 3, SQLAlchemy, SQLite, Jinja2, Bootstrap 5, scikit-learn, Chart.js, ReportLab, waitress, PyInstaller

> **Masaüstü uygulaması:** `python build_exe.py --kisayol` → masaüstündeki ikona çift tıklayın. Ayrıntılar: [`docs/MASAUSTU_KILAVUZU.md`](docs/MASAUSTU_KILAVUZU.md)
> **Final:** [`docs/FINAL_RAPORU.md`](docs/FINAL_RAPORU.md) · [`docs/FINAL_SOZLU_HAZIRLIK.md`](docs/FINAL_SOZLU_HAZIRLIK.md)

## Kurulum

```bash
python -m venv venv
venv\Scripts\Activate.ps1          # Windows  (macOS/Linux: source venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env             # macOS/Linux: cp .env.example .env  → SECRET_KEY değerini doldurun
flask kurulum --demo               # TEK KOMUT: tablolar, roller, kategoriler, demo hesapları, fiyatlar, AI tahminleri, siparişler
python run.py                      # http://127.0.0.1:5000   (geliştirme sunucusu)

# Temiz başlangıç (TÜM verileri siler, onay ister):  flask kurulum --sifirla --demo
# Mevcut bir veri tabanını güncellemek için:          flask db upgrade
```

## Demo hesapları

Tüm hesapların parolası: `Demo12345`

| Rol | E-posta | Ne yapabilir |
|---|---|---|
| Üretici | `ciftci@demo.com` | Ürün, ilan, gelen sipariş yönetimi (Genç Organik Çiftliği) |
| Üretici | `arici@demo.com` | Bal ürünleri (Solhan Bal Evi) |
| Müşteri | `musteri@demo.com` | Pazar, sepet, sipariş |
| Müşteri | `musteri2@demo.com` | İkinci demo müşterisi (raporlarda farklı müşteri sayısı için) |
| Yönetici | `admin@demo.com` | Kategoriler, tüm siparişler, istatistikler, platform raporları |

## Testler

```bash
pytest -v          # 353 test (internete çıkmaz; harici API'ler taklit edilir)
```

| Dosya | Kapsam |
|---|---|
| `test_models.py` | Tablolar ve ilişkiler |
| `test_auth.py` | Kayıt, giriş, çıkış, rol tabanlı erişim |
| `test_producer.py`, `test_categories.py` | Üretici profili, ürün CRUD, görsel yükleme, kategoriler |
| `test_listings.py`, `test_cart.py`, `test_orders.py` | İlan, sepet, sipariş, transaction, durum makinesi |
| `test_integration.py` | Uçtan uca akış, rol bazlı sayfa taraması, CSRF, hata sayfaları |
| `test_integrations.py` | Harici API katmanı: zaman aşımı, yeniden deneme, 429, hız sınırı, imza, idempotency (mock) |
| `test_payments.py`, `test_prices.py` | Ödeme akışı, iade, ödenmeyen sipariş iptali; fiyat senkronu ve karşılaştırma |
| `test_ai.py` | Tahmin algoritması (bilinen serilerle), öneri kuralları, tahmin kaydı, panellerdeki kartlar |
| `test_search.py` | Türkçe duyarsız arama, il/ilçe, fiyat aralığı, organik, doğrulanmış üretici, sıralamalar, sayfalama |
| `test_reports.py` | Dönem seçimi, ciro hesabı, saat dilimi sınırı, rol/IDOR kapsamı, CSV (BOM, formül enjeksiyonu), PDF |
| `test_deployment.py` | Log ve istek kimliği, 500 sayfası, `/saglik`, `flask kurulum`, `/medya`, masaüstü başlatıcısı (gerçek sunucu), .exe derleme argümanları |
| `test_security.py` | Güvenlik başlıkları/CSP, XSS, SQL injection, CSRF, IDOR (404), rol ihlali (403), toplu atama, brute force ve hız sınırları, N+1 sorgu sayısı, indeksler |

## Mimari

Veritabanı şeması (14 tablo): [`docs/ER_DIYAGRAMI.md`](docs/ER_DIYAGRAMI.md)

Katmanlı mimari: **Sunum** (`routes/`, `forms/`, `templates/`) → **İş mantığı** (`services/`) → **Veri erişimi** (`repositories/`) → **Veri** (`models/`).
Ayrıntılar: [`docs/VIZE_RAPORU.md`](docs/VIZE_RAPORU.md)

```
app/
├── models/         # 14 tablo (SQLAlchemy)
├── ai/             # Yapay zekâ: trend_model (tahmin), sell_advisor (öneri) — Flask'tan bağımsız (Hafta 10)
├── integrations/   # Harici API'ler: http_client, price_api, payment_gateway (Hafta 9)
├── reports/        # Rapor dönemi, hesaplama, CSV ve PDF üretimi — veritabanından bağımsız (Hafta 12)
├── bootstrap.py    # Veri tabanını tek adımda hazırlama (flask kurulum + masaüstü) (Hafta 13)
├── logging_setup.py  # Dönen log dosyaları, istek kimliği (Hafta 13)
├── repositories/   # Tüm sorgular; atomik stok güncellemeleri
├── services/       # İş kuralları (auth, producer, category, listing, cart, order, payment, price, prediction, search, report)
├── routes/         # Blueprint'ler: main, auth, producer, admin, market, cart, orders, payments, prices, reports, system
├── forms/          # Flask-WTF formları (CSRF + doğrulama)
├── utils/          # Dekoratörler (@role_required), görsel yükleme, biçimlendirme, Türkçe arama, pazar filtresi
├── templates/      # Jinja2 + Bootstrap 5
└── static/
scripts/            # seed_data.py, demo_data.py, download_assets.py (Bootstrap/Chart.js yerel kopyası)
desktop/            # Masaüstü başlatıcısı, kontrol penceresi, ikon (Hafta 13)
desktop_app.py      # Masaüstü giriş noktası · build_exe.py: PyInstaller ile .exe
tests/              # pytest
docs/               # Vize raporu, AI kullanım günlüğü, sözlü sınav hazırlığı
```

## Faydalı komutlar

| Komut | Açıklama |
|---|---|
| `flask kurulum [--demo] [--sifirla]` | Veri tabanını tek komutla hazırlar (Hafta 13) |
| `flask seed-db` | Yalnızca rolleri ve kategorileri ekler |
| `flask seed-demo` | Demo hesapları, ürünleri, ilanları ve siparişleri ekler (tekrar çalıştırılabilir) |
| `flask create-admin` | Yeni yönetici hesabı açar |
| `flask fetch-prices --days 30` | Hal fiyatlarını sağlayıcıdan çeker (geçmiş günler dahil) |
| `flask predict-prices` | Satıştaki tüm ürünler için 7 günlük AI fiyat tahmini üretir |
| `flask cancel-unpaid --hours 24` | Süresi dolan ödenmemiş siparişleri iptal eder, stoğu serbest bırakır |
| `flask db migrate -m "açıklama"` / `flask db upgrade` | Model değişikliğini veri tabanına uygular |

## Harici API'ler (Hafta 9)

`.env` içindeki `USE_MOCK_APIS=true` iken internete çıkılmaz: sahte hal fiyatı sağlayıcısı ve test ödeme
sağlayıcısı kullanılır. Gerçek / sandbox servise geçmek için `USE_MOCK_APIS=false` yapıp `PRICE_API_*` ve
`PAYMENT_API_*` değişkenlerini doldurun. Anahtarlar yalnızca `.env` dosyasında durur.

Test kartları (yalnızca sahte sağlayıcıda; son kullanma: gelecekte herhangi bir tarih, CVC: 3 rakam):

| Kart | Sonuç |
|---|---|
| `4111 1111 1111 1111` | Başarılı |
| `4000 0000 0000 0002` | Reddedilir |
| `4000 0000 0000 9995` | Yetersiz bakiye |
| `4000 0000 0000 0119` | Zaman aşımı (tekrar denemede aynı ödeme döner, çift çekim olmaz) |

## Yapay zekâ: fiyat tahmini (Hafta 10)

Son 30 günün hal fiyatına doğrusal regresyon uygulanarak 7 gün sonrası tahmin edilir; trend yönü, %95
tahmin aralığı ve geri teste dayalı güven skoru hesaplanır. Üretici panelinde ve ilan formunda fiyat önerisi,
müşteri panelinde ve fiyat sayfalarında trend grafiği gösterilir. Ayrıntılar: [`docs/MODEL_KARTI.md`](docs/MODEL_KARTI.md)

## Güvenlik ve performans (Hafta 11)

- **Güvenlik başlıkları:** istek başına nonce'lu CSP, `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy`, üretimde HSTS.
- **Yetkilendirme:** rol ihlali → `403`; başkasının ürünü/ilanı/siparişi → `404` (sorgular sahibe göre filtrelenir).
- **Brute force:** aynı hesaba 15 dakikada 5 hatalı giriş → kilit; IP başına dakikada 20 giriş, saatte 10 kayıt, dakikada 30 sepete ekleme.
- **Performans:** sık sorgulanan sütunlara indeksler, listelerde `selectinload` / `joinedload` / `contains_eager`.
  Geliştirme ortamında her yanıtın `X-Query-Count` başlığı o sayfanın kaç SQL sorgusu çalıştırdığını gösterir.
- Ayrıntılar ve tehdit → önlem → test tablosu: [`docs/GUVENLIK_DENETIMI.md`](docs/GUVENLIK_DENETIMI.md)

Hafta 11 yeni indeksler eklediği için bir kez migration çalıştırın:

```bash
flask db migrate -m "hafta 11 indeksler"
flask db upgrade
```

## Arama, raporlama ve dışa aktarma (Hafta 12)

- **Pazar filtreleri:** kategori, il/ilçe, fiyat aralığı, organik, doğrulanmış üretici; 6 sıralama seçeneği.
  Arama Türkçe karakter ve büyük/küçük harf duyarsızdır (`cilek` → "Çilek") ve ilan, ürün, çiftlik, bölge,
  kategori ve açıklamada arar. Tüm seçimler adres çubuğunda durur (paylaşılabilir bağlantı).
- **Raporlar** (`/raporlar/`): üretici kendi satışlarını, yönetici tüm platformu (veya tek bir üreticiyi) görür.
  Tarih aralıklı ciro, sipariş sayısı, ortalama sipariş, iptal oranı, günlük/aylık grafik, en çok satan ürünler,
  kategori ve üretici kırılımı.
- **Dışa aktarma:** CSV (Türkçe Excel uyumlu) ve PDF (Türkçe yazı tipi gömülü).
- Ayrıntılar: [`docs/ARAMA_VE_RAPORLAMA.md`](docs/ARAMA_VE_RAPORLAMA.md)

Hafta 12 yeni bir paket (`reportlab`) ve bir indeks (`orders.created_at`) ekler:

```bash
pip install -r requirements.txt
flask db migrate -m "hafta 12 rapor indeksi"
flask db upgrade
```

## Dağıtım ve masaüstü uygulaması (Hafta 13)

| Konu | Nasıl |
|---|---|
| Üretim sunucusu | `FLASK_ENV=production` + `.env` içinde ≥ 32 karakter `SECRET_KEY`, sonra `waitress-serve --host 127.0.0.1 --port 8000 --call app:create_app` |
| Log | `logs/uygulama.log` (1 MB × 5); her satırda istek kimliği; 500 sayfası yalnızca "hata kodu" gösterir |
| Sağlık kontrolü | `GET /saglik` → 200 / 503 |
| İnternetsiz ön yüz | `python scripts/download_assets.py` (Bootstrap, ikonlar, Chart.js → `app/static/vendor/`) |
| Masaüstü (geliştirirken) | `python desktop_app.py` (kontrol penceresi + tarayıcı), `--pencere` (pywebview), `--sifirla` |
| .exe | `pip install -r requirements-desktop.txt` → `python build_exe.py --kisayol` → `dist/TarladanSofraya/TarladanSofraya.exe` |

Masaüstü verileri: `%LOCALAPPDATA%\TarladanSofraya\` (veri.db, uploads, logs, gizli anahtar).
Hafta 13'te şema değişikliği yoktur (migration gerekmez); yalnızca `pip install -r requirements.txt` (waitress).
