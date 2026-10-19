# Final Hazırlığı: Demo Senaryosu ve Sözlü Sınav Yanıtları

## 1. Teslim öncesi

```bash
pytest -v                                   # 353 test geçmeli
git add . && git commit -m "Hafta 13: dağıtım, paketleme, masaüstü uygulaması"
git tag -a v0.13.0 -m "Final: masaüstü uygulaması" && git push && git push --tags
python build_exe.py --kisayol               # .exe (Windows)
```

`.exe` git deposuna eklenmez (`dist/` .gitignore'da). Paylaşmak için `dist\TarladanSofraya` klasörünü
zipleyip GitHub'da **Releases → v0.13.0** altına ekleyin.

## 2. Canlı demo senaryosu (≈ 5 dakika)

Sunumdan önce: `TarladanSofraya.exe --sifirla` (ya da `python desktop_app.py --sifirla`) → temiz demo verisi.
İnternet bağlantısını kapatın: uygulamanın internetsiz çalıştığını göstermek güçlü bir mesajdır.

| Süre | Adım | Söylenecek |
|---|---|---|
| 0:00 | Masaüstündeki ikona çift tıkla; kontrol penceresi ve tarayıcı açılır | "Python kurulu olmayan bir bilgisayarda da çalışır; sunucu yalnızca bu bilgisayarda dinliyor." |
| 0:30 | Pazar: `cilek` yaz, il = Bingöl, organik, fiyata göre sırala | "Türkçe karakter duyarsız arama; tüm filtreler adres çubuğunda." |
| 1:15 | `musteri@demo.com` ile giriş → sepete ekle → sipariş → test kartıyla öde | "Stok tek bir koşullu UPDATE ile düşer; aynı ürünü iki kişi aynı anda alamaz." |
| 2:15 | `ciftci@demo.com` → panel: AI tahmin kartı, ilan formunda önerilen fiyat | "Doğrusal regresyon + geri test; güven düşükse öneri vermiyor." |
| 3:00 | Raporlar → son 30 gün → PDF indir | "Tek sorgu, Türkiye saatiyle gün sınırı, PDF'e gömülü Türkçe yazı tipi." |
| 3:45 | Adres çubuğunda `?uretici=<başka id>` dene | "Üretici başkasının verisini göremez; kapsam oturumdan gelir (IDOR)." |
| 4:15 | `/saglik` adresini aç; kontrol penceresinde **Veri klasörü** → `logs\uygulama.log` | "İzleme için sağlık kontrolü; her log satırında istek kimliği." |
| 4:45 | Kontrol penceresi → **Kapat**; tekrar aç, veriler duruyor | "Veriler kullanıcının klasöründe; program güncellenince kaybolmaz." |

Yedek plan: `.exe` açılmazsa `python desktop_app.py` (aynı akış); o da olmazsa `flask kurulum --demo && python run.py`.

## 3. Hafta 13 sözlü sınav yanıtları

**S1. Uygulamayı nasıl paketlediniz? Çift tıklayınca ne oluyor?**
PyInstaller, Python yorumlayıcısını, paketleri, şablonları, statik dosyaları ve PDF yazı tipini tek bir
klasöre (`dist\TarladanSofraya`) koyar. Çift tıklayınca `desktop_app.py` çalışır: veri klasörünü hazırlar,
uygulama zaten açıksa onu gösterir, gizli anahtarı yükler/üretir, veri tabanını hazırlar, waitress sunucusunu
127.0.0.1'de boş bir portta başlatır, tarayıcıyı ve küçük bir kontrol penceresi açar. Pencere kapanınca
sunucu düzgünce durur.

**S2. Veriler neden .exe'nin yanında değil?**
.exe "Program Files" gibi yazılamayan bir yere konabilir; tek dosya modunda her açılışta geçici bir klasöre
açılır ve kapanınca silinir. Veri tabanı, yüklenen görseller, loglar ve gizli anahtar
`%LOCALAPPDATA%\TarladanSofraya` altında tutulur. Bu yüzden görseller `/static` yerine `/medya` adresinden
verilir: statik dosyalar uygulamanındır (salt-okunur), yüklemeler kullanıcının verisidir.

**S3. Sunucu neden 127.0.0.1'de, neden 0.0.0.0 değil?**
0.0.0.0 tüm ağ arayüzlerinde dinler; aynı Wi-Fi'deki herkes uygulamaya bağlanabilirdi. 127.0.0.1 yalnızca bu
bilgisayardan erişime izin verir. Bu yüzden masaüstünde HTTPS olmadan çalışmak (Secure çerez kapalı) kabul
edilebilir: trafik bilgisayardan çıkmaz.

**S4. Gizli anahtar .exe'de nasıl yönetiliyor?**
Koda veya pakete yazılmaz; `.env` pakete girmez. İlk açılışta `secrets.token_hex(32)` ile üretilip veri
klasöründe saklanır; sonraki açılışlarda aynı anahtar kullanılır (oturumlar düşmez). Her bilgisayarın
anahtarı farklıdır. Anahtar 32 karakterden kısaysa uygulama başlamaz.

**S5. Neden Flask'ın kendi sunucusu (app.run) değil de waitress?**
`app.run` geliştirme içindir: performans ve güvenlik için tasarlanmamıştır, Flask da üretimde kullanılmamasını
söyler. waitress saf Python'dur, Windows'ta çalışır (gunicorn çalışmaz), çok iş parçacıklıdır. Sunucuda da
aynı komutla kullanılabilir: `waitress-serve --call app:create_app`.

**S6. Üretim ayarları geliştirmeden nasıl ayrılıyor?**
`config.py` içinde ortam sınıfları: Development (DEBUG, sorgu sayacı), Testing (bellekte veri tabanı, CSRF
kapalı, mock API), Production (DEBUG kapalı, Secure çerez, dosyaya log, istek logu), Desktop (Production'dan
türer; yerel HTTP için Secure çerez kapalı, mock API). Ortam `FLASK_ENV` ile seçilir; bilinmeyen ad hata verir.
Gizli değerler yalnızca ortam değişkeninden okunur.

**S7. Log mekanizmanızı anlatın.**
Üretimde `logs/uygulama.log`'a yazılır; 1 MB dolunca döner, en fazla 5 eski dosya kalır (disk dolmaz). Her
isteğe 12 karakterlik bir kimlik verilir; yanıt başlığında (`X-Request-ID`), 500 sayfasında ve o isteğin
tüm log satırlarında görünür. Kullanıcı "hata kodu" bildirince logda aranır. Sorgu metni, parola ve çerez
loglanmaz. Dışarıdan gelen kimlik yalnızca güvenli biçimdeyse kabul edilir (log enjeksiyonuna karşı).

**S8. 500 hatasında kullanıcı ne görüyor, siz ne görüyorsunuz?**
Kullanıcı: "Beklenmeyen bir hata oluştu" ve hata kodu; traceback, SQL veya dosya yolu görmez (bilgi sızıntısı
olur). Biz: logda aynı kodla tam traceback. Yarım kalan veri tabanı işlemi geri alınır (rollback).

**S9. /saglik ne işe yarar?**
Uygulama ve veri tabanı ayakta mı? `SELECT 1` çalıştırır; başarılıysa 200, değilse 503 döner. İzleme
araçları ve yük dengeleyiciler bunu düzenli çağırır. Masaüstü başlatıcısı da sunucunun hazır olduğunu ve
ikinci kopyanın açık olup olmadığını bununla anlar. İç hata ayrıntısı dönmez.

**S10. "Tek komutla kurulum" neyi çözüyor?**
`flask kurulum --demo`: tabloları oluşturur, roller ve kategorileri ekler, demo verisini yükler. Tekrar
çalıştırmak güvenlidir (idempotent): var olanı silmez, kopya eklemez. `--sifirla` her şeyi siler ama onay
ister. Yeni veri tabanı Alembic'e "head" olarak işaretlenir; sonra `flask db upgrade` çakışmaz. Aynı fonksiyon
masaüstü uygulamasının ilk açılışında da kullanılır (kod tekrarı yok).

**S11. Uygulama internetsiz nasıl çalışıyor?**
Bootstrap, ikonlar ve Chart.js derlemeden önce `app/static/vendor/` altına indirilir; şablonlar yerel kopya
varsa onu kullanır. Harici API'ler masaüstünde sahte modda. Yapay zekâ modeli yerel çalışır.

**S12. Bu hafta nasıl test ettiniz?**
`test_deployment.py` (33 test): veri klasörü yolları, gizli anahtar üretimi, port seçimi, gerçek bir sunucuyu
başlatıp durdurma, tek kopya kontrolü, PyInstaller argümanlarında `.env`/yüklemeler olmaması, log dosyası ve
istek kimliği, 500 sayfasında iç ayrıntı olmaması, sağlık kontrolü (veri tabanı hatası dahil), `flask kurulum`,
`/medya` yol saldırısı. En önemlisi uçtan uca test: başlatıcı gerçek uygulamayla açılır, `/saglik` ve
`/pazar/` gerçek HTTP ile çağrılır, kapanınca sunucunun durduğu doğrulanır. `.exe` derlemesinin kendisi
Windows'ta elle denenir (otomatik testte PyInstaller çalıştırılmaz; birkaç dakika sürer).

## 4. Genel sözlü soru bankası (tüm dönem)

**Mimariyi 1 dakikada anlat.** Katmanlı: rota (HTTP) → servis (iş kuralı) → depo (sorgu) → model. 11 Blueprint,
14 tablo. Aynı servisler web, CLI, masaüstü ve testlerden çağrılır.

**Parolalar nasıl saklanıyor?** Werkzeug `generate_password_hash` (tuzlu, yavaş hash). Düz metin hiçbir yerde
yok; giriş `check_password_hash` ile. Olmayan e-postada da sahte hash doğrulanır (zamanlama saldırısı).

**Stok yarışını (race condition) nasıl önlediniz?** Koşullu UPDATE; etkilenen satır sayısıyla kontrol;
tek transaction; hata olursa rollback.

**Sipariş durumları nasıl yönetiliyor?** Durum makinesi: bekliyor → ödendi → kargoda → teslim; iptal yalnızca
belirli durumlardan ve belirli rollerle. Geçiş de koşullu UPDATE (aynı anda iki iptal stoğu iki kez geri eklemez).

**Harici API çökerse?** Zaman aşımı + yeniden deneme; yine olmazsa kullanıcıya anlaşılır mesaj, yarım veri
yazılmaz. Ödemede idempotency anahtarı çift çekimi önler.

**Yapay zekâ modelin ne kadar güvenilir?** Geri testte naif tahminle kıyaslanır, hata (MAPE) ve tahmin aralığı
gösterilir; güven %40'ın altındaysa "bekle/sat" önerisi verilmez. Mevsimsellik yok (veri kısa).

**IDOR nedir, 403 mü 404 mü?** Başkasının kaydına id ile erişim. Sorgu sahibine göre süzülür → 404 (kaydın
varlığını sızdırmamak için). Rol ihlali → 403.

**N+1 nedir?** Liste için 1 + her satır için 1 sorgu. `selectinload`/`joinedload` ile sabit sayıda sorgu;
testler `X-Query-Count` ile doğrular.

**CSV formül enjeksiyonu?** `=`, `+`, `-`, `@` ile başlayan hücrelere `'` eklenir; Excel formül çalıştırmaz.

**Projede en çok neyi öğrendin / tekrar yapsan neyi değiştirirdin?** [Kendi cevabınız: ör. testlerin yanlış
alarm verebileceği (Hafta 12), saat dilimi ve paketleme gibi "görünmeyen" işlerin süresi; baştan PostgreSQL ve
Docker ile başlamak.]
