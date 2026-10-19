# Arama, Filtreleme ve Raporlama (Hafta 12)

## 1. Pazar yeri filtreleri

Tüm seçimler adres çubuğunda durur (`GET` formu). Sonuç sayfası paylaşılabilir, yer imine eklenebilir;
geri tuşu doğru çalışır ve JavaScript kapalıyken de filtreler çalışır.

| Parametre | Örnek | Anlamı |
|---|---|---|
| `q` | `q=organik bal` | Metin araması (aşağıya bakın) |
| `kategori` | `kategori=4` | Kategori; üst kategori seçilirse alt kategoriler de dahil |
| `il`, `ilce` | `il=Bingöl&ilce=Genç` | Üreticinin bölgesi |
| `min_fiyat`, `max_fiyat` | `min_fiyat=12,5` | Birim fiyat aralığı (sınırlar dahil, Türkçe ondalık kabul edilir) |
| `organik` | `organik=1` | Yalnızca organik ürünler |
| `dogrulanmis` | `dogrulanmis=1` | Yalnızca doğrulanmış (sertifikalı) üreticiler |
| `sirala` | `ilgi`, `yeni`, `fiyat_artan`, `fiyat_azalan`, `degerlendirme`, `puan` | Sıralama |

**Geçersiz girdi asla hata (500) üretmez.** `MarketFilter.from_args()` (app/utils/market_filter.py) her değeri
doğrular: sayı olmayan fiyat yok sayılır, ters girilmiş fiyat aralığı düzeltilip kullanıcıya not gösterilir,
bilinmeyen sıralama varsayılana döner, olmayan kategori yok sayılır.

**Kararlı sıralama:** Her sıralamanın sonuna `id` eklenir. Aynı fiyatlı iki ilan sayfalar arasında yer
değiştirmez (aksi hâlde bir ilan hem 1. hem 2. sayfada görünebilir ya da hiç görünmeyebilir).

### İl / ilçe

Üretici bölgesini serbest metin olarak yazar (`Bingöl / Genç`, `bingöl/genç`, `BİNGÖL`). `RegionIndex` bu
yazımları Türkçe duyarsız olarak gruplar ve filtre listesini yalnızca **satışta ilanı olan** üreticilerden
üretir. Filtreleme veritabanındaki ham değerlerle yapılır: `region IN ('Bingöl / Genç', 'bingöl/genç')`.

## 2. Metin araması

- Arama metni kelimelere bölünür (en fazla 5 kelime, 100 karakter). **Her kelime** şu alanlardan en az birinde
  geçmelidir (AND): ilan başlığı, ürün adı, ürün açıklaması, çiftlik adı, bölge, kategori adı.
- Kelimenin bir parçası da eşleşir (partial match): `sal` → "Salkım Domates".
- **Türkçe duyarsızlık:** SQLite'ın `LOWER()` / `LIKE` işlemi yalnızca İngilizce harfleri tanır. Bu yüzden
  SQLite'a `tr_fold()` adında bir fonksiyon kaydedilir (app/extensions.py). Fonksiyon hem sütuna hem aranan
  kelimeye uygulanır: `ÇİLEK`, `çilek`, `cilek`, `CILEK` → `cilek`.
- `%` ve `_` joker karakterleri kaçırılır (Hafta 11, `contains_pattern`). Kullanıcı girdisi her zaman
  parametre olarak gönderilir; SQL'e metin olarak eklenmez.
- **En ilgili** sıralaması (yalnızca arama yapılınca): başlıkta geçen kelime 3, ürün adında 2, çiftlik adında
  1 puan; eşitlikte en yeni ilan önce.

### Bilinen sınır ve büyüme yolu

`LIKE '%kelime%'` indeks kullanamaz; her aramada filtrelenen ilanlar baştan sona taranır. Satıştaki ilan sayısı
birkaç bin olduğu sürece bu milisaniyeler sürer. Veri büyürse:

1. **SQLite FTS5** sanal tablosu (tam metin dizini, `MATCH` sorgusu, `bm25()` ile ilgi puanı), ya da
2. **PostgreSQL**: `unaccent` + `pg_trgm` (trigram) indeksi veya `tsvector` tam metin araması.

Uygulama katmanı değişmez; yalnızca `ListingRepository.search_available()` güncellenir.

## 3. Raporlar

| Rol | Görebildiği | Nasıl sağlanıyor |
|---|---|---|
| Yönetici | Tüm platform; isterse tek bir üretici (`?uretici=<id>`) | `report_service.resolve_scope` |
| Üretici | Yalnızca kendi kalemleri | Kapsam `current_user.producer_profile`'dan gelir; URL'deki `uretici` **yok sayılır** (IDOR) |
| Müşteri | — | `@role_required` → `403` |

**Ciro tanımı:** Ödenmiş, kargodaki ve teslim edilmiş siparişlerin kalem tutarları
(miktar × sipariş anındaki birim fiyat). Ödeme bekleyen ve iptal edilen siparişler ciroya girmez; ayrı gösterilir.

**Dönem:** Hazır (`?donem=7g|30g|bu_ay|gecen_ay|bu_yil`) veya özel (`?baslangic=2026-10-01&bitis=2026-10-19`).
En fazla 366 gün. 62 günden uzun dönemler aylık, kısalar günlük gruplanır.

**Saat dilimi:** Veritabanındaki saatler UTC'dir. "19 Ekim" Türkiye saatiyle 18 Ekim 21:00 UTC'de başlar.
`ReportPeriod.utc_bounds()` bu çeviriyi yapar; gece 00:00–03:00 arasındaki siparişler doğru güne yazılır.

**Tek sorgu:** `ReportRepository.order_item_rows()` dönemdeki kalemleri sipariş, müşteri, üretici, ürün ve
kategori bilgisiyle birlikte TEK sorguda getirir (ORM nesnesi değil, yalnızca gereken sütunlar). Toplamlar
`app/reports/builder.py` içinde hesaplanır; ekran, CSV ve PDF aynı sonucu kullanır.
Satır sayısı `REPORT_MAX_ROWS` (50.000) ile sınırlıdır; aşılırsa kullanıcıdan dönemi daraltması istenir
(kesilmiş veriyle yanlış toplam göstermek yerine).

## 4. Dışa aktarma

| Biçim | Adres | Ayrıntı |
|---|---|---|
| CSV | `/raporlar/indir/csv?tablo=siparisler\|urunler\|donemler` | UTF-8 + BOM, `;` ayırıcı, `1234,50` sayı biçimi → Türkçe Excel'de doğrudan açılır |
| PDF | `/raporlar/indir/pdf` | ReportLab, A4; özet kartları, ciro grafiği, tablolar, sayfa numarası |

Güvenlik ve sağlamlık:

- **CSV/formül enjeksiyonu:** Ürün adını üretici yazar. `=`, `+`, `-`, `@`, sekme ile başlayan metinlerin başına
  `'` eklenir; Excel bunları formül olarak çalıştırmaz.
- **PDF'te Türkçe karakter:** Standart PDF yazı tipleri `ğ ş ı İ ₺` içermez; DejaVu Sans PDF'e gömülür
  (`app/reports/fonts/`, lisansı aynı klasörde). Dosya yoksa Helvetica'ya dönülür, rapor yine üretilir.
- PDF'te kullanıcı verisi `escape()` edilir (ReportLab paragrafları küçük bir HTML alt kümesini yorumlar).
- `Cache-Control: no-store`: satış verisi tarayıcı veya ara sunucu önbelleğine yazılmaz.
- İndirme hız sınırı: kullanıcı başına dakikada 10 (`REPORT_EXPORTS_PER_MIN`); PDF üretimi pahalıdır.
- Dosyalar bellekte üretilir (BytesIO); sunucuda geçici dosya kalmaz.
