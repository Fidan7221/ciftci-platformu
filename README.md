# Tarladan Sofraya — Çiftçi Doğrudan Satış ve Fiyat Takip Platformu (P11)

Bingöl Üniversitesi Bilgisayar Programcılığı dönem projesi.
Çiftçilerin ürünlerini aracısız satabildiği, müşterilerin doğrudan üreticiden alışveriş yaptığı bir pazar yeri.

**Sürüm:** `v0.10.0` · **Teknoloji:** Python 3.11+, Flask 3, SQLAlchemy, SQLite, Jinja2, Bootstrap 5, scikit-learn, Chart.js

## Kurulum

```bash
python -m venv venv
venv\Scripts\Activate.ps1          # Windows  (macOS/Linux: source venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env             # macOS/Linux: cp .env.example .env  → SECRET_KEY değerini doldurun
flask db upgrade                   # tabloları oluşturur
flask seed-demo                    # roller, kategoriler, demo verileri, 60 günlük hal fiyatı ve AI tahminleri
python run.py                      # http://127.0.0.1:5000
```

## Demo hesapları

Tüm hesapların parolası: `Demo12345`

| Rol | E-posta | Ne yapabilir |
|---|---|---|
| Üretici | `ciftci@demo.com` | Ürün, ilan, gelen sipariş yönetimi (Genç Organik Çiftliği) |
| Üretici | `arici@demo.com` | Bal ürünleri (Solhan Bal Evi) |
| Müşteri | `musteri@demo.com` | Pazar, sepet, sipariş |
| Yönetici | `admin@demo.com` | Kategoriler, tüm siparişler, istatistikler |

## Testler

```bash
pytest -v          # 183 test (internete çıkmaz; harici API'ler taklit edilir)
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

## Mimari

Katmanlı mimari: **Sunum** (`routes/`, `forms/`, `templates/`) → **İş mantığı** (`services/`) → **Veri erişimi** (`repositories/`) → **Veri** (`models/`).
Ayrıntılar: [`docs/VIZE_RAPORU.md`](docs/VIZE_RAPORU.md)

```
app/
├── models/         # 14 tablo (SQLAlchemy)
├── ai/             # Yapay zekâ: trend_model (tahmin), sell_advisor (öneri) — Flask'tan bağımsız (Hafta 10)
├── integrations/   # Harici API'ler: http_client, price_api, payment_gateway (Hafta 9)
├── repositories/   # Tüm sorgular; atomik stok güncellemeleri
├── services/       # İş kuralları (auth, producer, category, listing, cart, order, payment, price, prediction)
├── routes/         # Blueprint'ler: main, auth, producer, admin, market, cart, orders, payments, prices
├── forms/          # Flask-WTF formları (CSRF + doğrulama)
├── utils/          # Dekoratörler (@role_required), görsel yükleme, biçimlendirme
├── templates/      # Jinja2 + Bootstrap 5
└── static/
scripts/            # seed_data.py (roller, kategoriler), demo_data.py (vize demosu)
tests/              # pytest
docs/               # Vize raporu, AI kullanım günlüğü, sözlü sınav hazırlığı
```

## Faydalı komutlar

| Komut | Açıklama |
|---|---|
| `flask seed-db` | Yalnızca rolleri ve kategorileri ekler |
| `flask seed-demo` | Demo hesapları, ürünleri ve ilanları ekler (tekrar çalıştırılabilir) |
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
