# Model Kartı — Hal Fiyatı Trend Tahmini (`linreg-30g-v1`)

Model kartı, bir makine öğrenmesi modelinin ne yaptığını, nasıl değerlendirildiğini ve sınırlarını
kısaca belgeleyen standart bir dokümandır.

## Amaç
Üreticiye, ürününün hal (toptan) fiyatının önümüzdeki **7 gün** içinde hangi yöne gideceği hakkında
karar desteği vermek ve doğrudan satış için bir fiyat aralığı önermek. Müşteriye yalnızca tarafsız
trend bilgisi gösterilir.

## Veri
- Kaynak: `market_prices` tablosu (Hafta 9 fiyat sağlayıcısı; demo ortamında sahte sağlayıcı).
- Birim: ürün kategorisi başına günlük ortalama hal fiyatı (TL/kg).
- Pencere: son **30 gün**; en az **14 gün** veri yoksa tahmin yapılmaz.
- Temizleme: aynı gün birden çok kayıt ortalanır; sıfır/boş fiyatlar atılır; medyandan 3 MAD'den fazla
  sapan değerler sınıra çekilir (veri giriş hatalarına karşı).

## Yöntem
`fiyat = a + b × gün` doğrusal regresyonu (scikit-learn `LinearRegression`).

| Çıktı | Hesap |
|---|---|
| Tahmin | `a + b × (son gün + 7)`, en az 0,01 TL |
| Trend | haftalık değişim `b × 7 / son 7 gün ortalaması`; > +%2 artış, < −%2 düşüş, arası dengeli |
| %95 aralık | tahmin ± 1,96 × artıkların standart sapması |
| Güven (0-1) | `(1 − geri test MAPE / %15) × (0,5 + 0,5 × veri gün sayısı / 30)` |

## Değerlendirme
**Geri test (walk-forward backtest):** Geçmişteki 10 farklı günde, yalnızca o güne kadarki veriyle
7 gün sonrası tahmin edilir ve gerçekleşen fiyatla karşılaştırılır. Hata ölçüsü **MAPE**
(ortalama mutlak yüzde hata).

Model, **naif tahminle** (yani "7 gün sonra da fiyat bugünkü gibi olur" varsayımıyla) kıyaslanır.
Bir model naif tahmini geçemiyorsa işe yaramıyordur. Bu kıyas, `/fiyatlar/<ürün>` sayfasında
her ürün için gösterilir.

Sahte sağlayıcının 60 günlük verisiyle yapılan bir denemede:
- Model hatası: Domates %2,6, Elma %2,5, Kayısı %2,0
- Naif tahminin hatası: Domates %4,1, Elma %3,9, Kayısı %3,5

Bu ürünlerde model naif tahminden daha isabetli çıktı. Fiyatın yön değiştirdiği dönemlerde ise
(denemede Patates ve Nohut) naif tahmin biraz daha iyi sonuç verdi. Bu durum sayfada ayrıca uyarı
olarak gösterilir.

## Öneri kuralları (makine öğrenmesi değil, açık kurallar)
- Güven < 0,40 ise "bekle / sat" önerisi verilmez.
- Trend artış yönünde ve beklenen artış ≥ %3 ise "bekle" önerilir. Ürün hızlı bozulan bir sebze veya
  meyveyse ayrıca uyarı eklenir.
- Trend düşüş yönündeyse "şimdi sat" önerilir.
- Fiyat bandı: `temel = güncel + güven × (tahmin − güncel)`.
  - Taban fiyat: temel değerin kendisi.
  - Önerilen fiyat: temel + %15 (doğrudan satış primi).
  - Tavan fiyat: temel + %35.
  - Organik ürünlerde önerilen ve tavan fiyata %10 ek prim uygulanır.

## Sınırlar
- Model yalnızca fiyat geçmişini bilir. Hava koşulları, bayramlar, ihracat, don gibi dış etkenleri bilmez.
- Doğrusal modeldir; 7 günlük kısa vadede trendi yakalar ama mevsimsel dönüş noktalarını geç fark eder.
- Tahmin aralığı basitleştirilmiştir: tahmin ufku uzadıkça artan belirsizliği hesaba katmaz.
- Hal fiyatı toptan fiyattır; perakende fiyatı ile aynı değildir.
- Çıktılar karar desteğidir, kesin sonuç değildir. Arayüzde de bu şekilde belirtilir.
