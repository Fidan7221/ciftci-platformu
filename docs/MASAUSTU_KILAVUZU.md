# Masaüstü Uygulaması (.exe) Kılavuzu — Hafta 13

Bu kılavuz, projeyi **çift tıklayınca açılan** bir Windows uygulamasına dönüştürmeyi anlatır.
Üretilen uygulama internet olmadan da çalışır (sunum, final).

## 1. Nasıl çalışır?

```
TarladanSofraya.exe
   │
   ├─ 1. Veri klasörü:  %LOCALAPPDATA%\TarladanSofraya\
   │        veri.db (SQLite) · uploads\ (ürün görselleri) · logs\ · gizli_anahtar.txt
   ├─ 2. Zaten açıksa → açık olanı tarayıcıda gösterir, ikinci kopya başlamaz
   ├─ 3. İlk açılış → tablolar + roller/kategoriler + demo verileri (hesaplar, ürünler, fiyatlar, siparişler)
   ├─ 4. Sunucu (waitress) → yalnızca 127.0.0.1, boş bir port (5050-5059)
   └─ 5. Tarayıcı açılır + küçük kontrol penceresi ("Tarayıcıda aç", "Veri klasörü", "Kapat")
            Kontrol penceresi kapanınca sunucu da düzgünce kapanır.
```

Neden veriler `.exe`'nin yanında değil? `.exe` "Program Files" gibi yazılamayan bir klasöre konabilir,
tek dosya modunda ise her açılışta geçici bir klasöre açılır. Veriler kullanıcının kendi klasöründe
durunca program güncellense de silinse de veriler korunur.

## 2. Derleme (bir kez, Windows bilgisayarda)

```powershell
cd ciftci-platformu
venv\Scripts\Activate.ps1
pip install -r requirements-desktop.txt     # PyInstaller + Pillow (+ uygulama paketleri)
python build_exe.py --kisayol
```

`build_exe.py` sırasıyla:

1. Bootstrap, Bootstrap Icons ve Chart.js dosyalarını `app/static/vendor/` altına indirir (**bu adım internet ister**;
   sonra uygulama internetsiz çalışır). Elle: `python scripts/download_assets.py`
2. İkon yoksa üretir (`desktop/icon.ico`). Elle: `python desktop/make_icon.py`
3. `app/static` klasörünü **kullanıcı yüklemeleri hariç** kopyalar (kendi test görselleriniz pakete girmez).
4. PyInstaller'ı çalıştırır (3-6 dakika).
5. `--kisayol` verildiyse masaüstüne **Tarladan Sofraya** kısayolu koyar.

Sonuç: `dist\TarladanSofraya\TarladanSofraya.exe` (yanındaki `_internal` klasörüyle birlikte).

| Seçenek | Ne yapar |
|---|---|
| (yok) | Klasör modu (`--onedir`): hızlı açılır, antivirüs uyarısı daha az. **Önerilen.** |
| `--tek-dosya` | Tek bir `.exe` (`--onefile`): taşıması kolay, her açılışta kendini geçici klasöre açtığı için ilk açılış yavaştır. |
| `--konsol` | Siyah konsol penceresi de açılır; başlamayan bir derlemenin hatasını görmek için. |
| `--kisayol` | Masaüstü kısayolu oluşturur (PowerShell, Windows Script Host). |
| `--cdn` | Ön yüz dosyalarını indirmeden derler (uygulama internet ister). |

## 3. İkon ve masaüstü kısayolu

- İkon dosyası: `desktop/icon.ico` (16-256 px, `.exe` ve kısayolda), `desktop/icon.png` (kontrol penceresi),
  `app/static/img/favicon.png` (tarayıcı sekmesi). Kodla çizilir (`desktop/make_icon.py`), telif sorunu yoktur.
- Kısayolu elle oluşturmak: `TarladanSofraya.exe`'ye sağ tık → **Gönder** → **Masaüstü (kısayol oluştur)**.
  Kısayolun adını "Tarladan Sofraya" yapın. Başlat menüsüne sabitlemek için sağ tık → **Başlangıç'a sabitle**.
- Başka bir bilgisayara taşımak: `dist\TarladanSofraya` klasörünün **tamamını** zipleyip kopyalayın
  (yalnızca `.exe`'yi değil). Hedef bilgisayarda Python kurulu olması gerekmez.

## 4. Derlemeden çalıştırma (geliştirirken)

```powershell
python desktop_app.py               # kontrol penceresi + tarayıcı
python desktop_app.py --pencere     # pip install pywebview yapıldıysa: tarayıcısız, kendi penceresinde
python desktop_app.py --konsol      # pencere yok; terminalde Ctrl+C ile kapanır
python desktop_app.py --sifirla     # tüm verileri silip temiz demo kurar (sunumdan önce)
python desktop_app.py --demo-yok    # ilk açılışta demo verisi ekleme
python desktop_app.py --veri-klasoru D:\deneme   # farklı veri klasörü
```

Demo hesapları (parola `Demo12345`): `ciftci@demo.com`, `arici@demo.com`, `musteri@demo.com`,
`musteri2@demo.com`, `admin@demo.com`.

## 5. Sunumdan önce kontrol listesi

- [ ] `python desktop_app.py --sifirla` ile temiz demo verisi (ya da `.exe`'yi bir kez `--sifirla` ile çalıştırın)
- [ ] İnternet kapalıyken açıp sayfaların stilli göründüğünü kontrol edin (ön yüz dosyaları pakette mi?)
- [ ] Raporlar → PDF indir (Türkçe karakterler doğru mu?)
- [ ] Kontrol penceresinden **Kapat** → tekrar açınca veriler duruyor mu?

## 6. Sorun giderme

| Belirti | Neden / Çözüm |
|---|---|
| "Windows kişisel bilgisayarınızı korudu" (SmartScreen) | `.exe` imzalı değil. **Ek bilgi → Yine de çalıştır.** Ders projesi için normaldir; ticari dağıtımda kod imzalama sertifikası gerekir. |
| Antivirüs `.exe`'yi siliyor | PyInstaller ile üretilen imzasız dosyalarda yanlış alarm görülebilir. Klasör modunu kullanın, `dist` klasörünü istisnaya ekleyin. |
| Açılmıyor, hiçbir şey görünmüyor | `%LOCALAPPDATA%\TarladanSofraya\logs\baslatma.log` dosyasına bakın; ya da `python build_exe.py --konsol` ile derleyip hatayı görün. |
| Sayfalar stilsiz | Derleme `--cdn` ile yapıldı ve internet yok. `python scripts/download_assets.py` sonra yeniden derleyin. |
| "Port kullanımda" | Başlatıcı 5050-5059 arasında boş port arar, yoksa işletim sistemine seçtirir. Sorun sürerse `--port 8123`. |
| Verileri sıfırlamak | Uygulamayı kapatın, `--sifirla` ile açın ya da veri klasöründeki `veri.db` dosyasını silin. |
| Hata sayfasında "hata kodu" | `logs\uygulama.log` içinde bu kodu aratın; o isteğe ait tüm satırlar bulunur. |

## 7. Güvenlik notları

- Sunucu `127.0.0.1`'de dinler: aynı ağdaki başka bir bilgisayar uygulamaya erişemez.
- Gizli anahtar ilk açılışta rastgele üretilir (`secrets.token_hex(32)`), koda veya pakete yazılmaz.
  `.env` dosyası pakete **girmez**.
- Yerel bağlantı HTTPS değildir; bu yüzden masaüstünde `SESSION_COOKIE_SECURE=False` kullanılır.
  Trafik bilgisayarın dışına çıkmadığı için risk oluşturmaz. Sunucuda (ProductionConfig) çerezler yalnızca HTTPS ile gönderilir.
- Harici API'ler masaüstünde sahte (mock) modda çalışır; gerçek ödeme alınmaz.

## 8. Sunucuya dağıtım (masaüstü dışı, bilgi için)

```bash
export FLASK_ENV=production SECRET_KEY=<64 karakter> DATABASE_URL=...
flask kurulum                                   # tablolar + roller/kategoriler (Alembic "head" işaretlenir)
waitress-serve --host 127.0.0.1 --port 8000 --call app:create_app
```

Önüne HTTPS sonlandıran bir ters vekil (Nginx/Caddy) konur; `/saglik` adresi izleme araçları içindir.
