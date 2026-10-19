# Yapay Zekâ Kullanım Günlüğü (güncel: Hafta 11)

**Kullanılan araç:** Claude (Anthropic), claude.ai sohbet arayüzü
**Kullanım biçimi:** Her hafta için gereksinimler istem olarak verildi; yapay zekâ kod, test ve açıklama üretti.
Kod VS Code'da projeye eklendi, testler **kendi bilgisayarımda** çalıştırıldı.

> Not: Yapay zekânın çalıştığı ortamda paket deposuna erişim kapalıydı; bu yüzden üretilen kodu orada
> çoğunlukla çalıştıramadı, sözdizimi ve statik analiz kontrolü yaptı. (Hafta 9'da harici API katmanının
> 23 testi, Hafta 10'da tahmin algoritmasının 20 testi orada da gerçekten çalıştırıldı.) Tüm "geçti" sonuçları benim
> bilgisayarımdaki `pytest` çıktısıdır.
>
> `[ ]` ile işaretli alanları kendi deneyiminize göre doldurun. Hoca bu bölümde sizin ne
> anladığınızı ve neyi değiştirdiğinizi görmek ister.

## Haftalık kayıtlar

| Tarih | Hafta | İstemin amacı | Yapay zekânın ürettiği | Benim kararım / doğrulamam | Sonuç |
|---|---|---|---|---|---|
| 18.10.2026 | 3-4 | Teknoloji yığını, klasör yapısı, ER şeması | Flask + SQLite önerisi, katmanlı klasör yapısı, 14 tablo, `config.py`, modeller, `seed_data.py` | Flask + SQLite ve Jinja2 + Bootstrap seçimini onayladım. [ ] | Uygulama çalıştı, 3 test geçti |
| 18.10.2026 | 5 | Kayıt, giriş, hashleme, rol erişimi | Formlar, `auth_service`, `@role_required`, giriş/kayıt şablonları, 13 test, sözlü yanıtlar | [ ] | 16 test geçti |
| 19.10.2026 | 6 | Üretici profili, ürün CRUD, görsel | Ürün/kategori servisleri, görsel imza kontrolü, sayfalama, 28 test | Ürün tablosuna stok alanı eklenmesi önerisini kabul ettim (migration). [ ] | 44 test geçti |
| 19.10.2026 | 7 | İlan, sepet, sipariş, transaction | Koşullu UPDATE ile stok düşürme, durum makinesi, sepetin üreticiye göre bölünmesi, 37 test | İki stok kuralını (aktif ilanlar ≤ ürün stoğu) kabul ettim. [ ] | Entegre edildi [test sayısını yazın] |
| 19.10.2026 | 8 | Vize: entegrasyon, düzeltme, belge | Entegrasyon taraması, 6 düzeltme, demo verisi, 14 entegrasyon testi, rapor ve sözlü hazırlık | [ ] | [ ] / 95 test |
| 19.10.2026 | 9 | Fiyat ve ödeme API entegrasyonu | Ortak HTTP istemcisi (timeout, retry, 429, hız sınırı), sahte/HTTP fiyat ve ödeme sağlayıcıları, idempotency, HMAC imzası, iade akışı, 56 test | [ ] | [ ] / 151 test |
| 19.10.2026 | 10 | Fiyat tahmini ve trend analizi | Doğrusal regresyon modeli, geri test, güven skoru, öneri kuralları, tahmin kaydı, grafik kartları, model kartı, 32 test | [ ] Model seçimi (neden doğrusal regresyon) ve öneri kurallarındaki prim oranlarını kendim değerlendirdim mi? | [ ] / 183 test |
| 19.10.2026 | 11 | Güvenlik, ince yetkilendirme, performans | Güvenlik denetimi (CSRF/XSS/SQLi/IDOR), CSP nonce + güvenlik başlıkları, LIKE joker kaçışı, hesap kilitleme ve hız sınırları, indeksler, N+1 düzeltmeleri (selectinload/joinedload/contains_eager), sorgu sayacı, `docs/GUVENLIK_DENETIMI.md`, 41 güvenlik testi | [ ] | [ ] / 224 test |

## Yapay zekânın hataları ve nasıl yakalandığı

Yapay zekâ çıktısı her zaman doğru değildi. Bir kısmını yapay zekâ teslimden önce kendi kontrolünde yakaladı;
bir kısmı ise teslim edilen koda girdi ve Hafta 8 entegrasyon taramasında bulundu:

| Hafta | Hata | Nasıl fark edildi | Düzeltme |
|---|---|---|---|
| 5 | Bootstrap Icons'ta bulunmayan `bi-tractor` simgesi kullanılmıştı | Teslim öncesi kontrol (yapay zekâ) | `bi-tree` ile değiştirildi |
| 6 | Şablonda `round` filtresiyle miktar biçimlendirmesi `100.0` gibi hatalı çıktı veriyordu | Teslim öncesi kontrol (yapay zekâ) | Ortak `qty` filtresi yazıldı (`100`, `12,5`) |
| 7 | `current_user` (bir vekil/LocalProxy nesnesi) doğrudan `Order(customer=...)` ilişkisine veriliyordu; SQLAlchemy gerçek nesne bekler | Teslim öncesi kontrol (yapay zekâ) | `_get_current_object()` ile gerçek nesne veriliyor (`_me()` yardımcısı) |
| 7 | Menü yenilenirken üreticinin "Profilim" bağlantısı kaldırılmıştı | Teslim edilen koddaydı; Hafta 8 entegrasyon taramasında bulundu | Kullanıcı açılır menüsüne eklendi |
| 7 | Saatler UTC gösteriliyordu | Teslim edilen koddaydı; Hafta 8 entegrasyon taramasında bulundu | `datetime_tr` filtresi UTC+3'e çeviriyor + test |
| 9 | Test dosyasında `db.update` kullanılmıştı; Flask-SQLAlchemy'nin bunu sağladığı kesin değildi | Teslim öncesi kontrol (yapay zekâ) | `sqlalchemy.update` doğrudan içe aktarıldı |
| 11 | Performans testinde `expunge_all()` kullanılmıştı; oturumdaki `current_user` nesnesi kopup `DetachedInstanceError` verirdi | Teslim öncesi kontrol (yapay zekâ) | `expire_all()` ile değiştirildi |
| 11 | `tojson` filtresi `₺` işaretini `\u20ba` olarak kaçırdığı için eski bir test (`test_prices.py`) kırılacaktı | Teslim öncesi kontrol (yapay zekâ) | Test, sembolden bağımsız `25,00` metnini arayacak şekilde güncellendi |
| [ ] | [Kendi bulduğunuz hatalar] | [ ] | [ ] |

## Öğrendiklerim / yapay zekânın sınırları

- [ ] Örn. "Yapay zekâ çalışan kod üretse de 'neden böyle?' sorusunu kendim sormazsam yarış durumu gibi sorunları göremezdim."
- [ ] Örn. "Testleri kendim çalıştırmadan hiçbir çıktıyı doğru kabul etmedim."
- Yapay zekâ, çalıştıramadığı kodu "doğrulandı" diye sunmadı; her teslimde neyin test edildiğini, neyin edilemediğini belirtti.

## Akademik dürüstlük beyanı

Projede yapay zekâ desteği kullanılmıştır ve bu günlükte kaydedilmiştir. Teslim edilen her kod parçasını okudum,
çalıştırdım ve sözlü sınavda açıklayabilecek düzeyde inceledim. [ ]
