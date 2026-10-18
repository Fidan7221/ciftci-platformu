# Tarladan Sofraya — Çiftçi Doğrudan Satış ve Fiyat Takip Platformu (P11)

Bingöl Üniversitesi Bilgisayar Programcılığı dönem projesi.
Çiftçilerin ürünlerini aracısız satabildiği, müşterilerin doğrudan üreticiden alışveriş yaptığı bir pazar yeri.

**Sürüm:** `v0.8.0-vize` (ara sürüm) · **Teknoloji:** Python 3.11+, Flask 3, SQLAlchemy, SQLite, Jinja2, Bootstrap 5

## Kurulum

```bash
python -m venv venv
venv\Scripts\Activate.ps1          # Windows  (macOS/Linux: source venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env             # macOS/Linux: cp .env.example .env  → SECRET_KEY değerini doldurun
flask db upgrade                   # tabloları oluşturur
flask seed-demo                    # roller, kategoriler ve demo verileri
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
pytest -v          # 95 test
```

| Dosya | Kapsam |
|---|---|
| `test_models.py` | Tablolar ve ilişkiler |
| `test_auth.py` | Kayıt, giriş, çıkış, rol tabanlı erişim |
| `test_producer.py`, `test_categories.py` | Üretici profili, ürün CRUD, görsel yükleme, kategoriler |
| `test_listings.py`, `test_cart.py`, `test_orders.py` | İlan, sepet, sipariş, transaction, durum makinesi |
| `test_integration.py` | Uçtan uca akış, rol bazlı sayfa taraması, CSRF, hata sayfaları |

## Mimari

Katmanlı mimari: **Sunum** (`routes/`, `forms/`, `templates/`) → **İş mantığı** (`services/`) → **Veri erişimi** (`repositories/`) → **Veri** (`models/`).
Ayrıntılar: [`docs/VIZE_RAPORU.md`](docs/VIZE_RAPORU.md)

```
app/
├── models/         # 14 tablo (SQLAlchemy)
├── repositories/   # Tüm sorgular; atomik stok güncellemeleri
├── services/       # İş kuralları (auth, producer, category, listing, cart, order)
├── routes/         # Blueprint'ler: main, auth, producer, admin, market, cart, orders
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
| `flask db migrate -m "açıklama"` / `flask db upgrade` | Model değişikliğini veri tabanına uygular |
