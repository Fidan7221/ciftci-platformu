// =====================================================================
// seed.js — Sentetik (yapay) örnek veri ile doldurma
//
// KVKK UYUMU — Bu dosyadaki verilerin HİÇBİRİ gerçek kişiye ait değildir:
//  * Gerçek ad-soyad YOK: kullanıcı adları "alici01", "uretici03" gibi üretilmiş kodlardır.
//  * E-postalar ".test" uzantılı: Bu uzantı internet standartlarında (RFC 2606)
//    test için ayrılmıştır, gerçek bir e-posta adresi OLAMAZ.
//  * TC kimlik, telefon, açık adres gibi kişisel veri alanları tabloda hiç yok.
//  * Çiftlik adları uydurmadır; il bilgisi kişiyi tanımlamaz.
//
// Çalıştırma:  npm run seed
// =====================================================================
const { baglan, islem } = require('./db');

// Rastgelelik "sabit tohumlu" (seeded) — her çalıştırmada AYNI veriler üretilir.
// Böylece hocaya gösterirken sonuçlar tutarlı olur.
let tohum = 42;
function rastgele() {
  tohum = (tohum * 1103515245 + 12345) % 2147483648;
  return tohum / 2147483648;
}
const sec = (dizi) => dizi[Math.floor(rastgele() * dizi.length)];
const yuvarla = (sayi) => Math.round(sayi * 100) / 100;

const KATEGORILER = [
  ['Sebze', 'Taze sebzeler'],
  ['Meyve', 'Mevsim meyveleri'],
  ['Süt Ürünleri', 'Peynir, yoğurt, tereyağı'],
  ['Arı Ürünleri', 'Bal, polen, propolis'],
  ['Kahvaltılık', 'Kahvaltı sofrası ürünleri'],
  ['Kuru Gıda', 'Kuruyemiş, bakliyat'],
];

// [ürün adı, birim, taban fiyat, kategori adları (N-N ilişki!)]
const URUNLER = [
  ['Domates', 'kg', 35, ['Sebze']],
  ['Biber', 'kg', 45, ['Sebze']],
  ['Maydanoz', 'demet', 10, ['Sebze']],
  ['Elma', 'kg', 30, ['Meyve']],
  ['Ceviz', 'kg', 280, ['Kuru Gıda', 'Kahvaltılık']],
  ['Süzme Bal', 'kg', 650, ['Arı Ürünleri', 'Kahvaltılık']],
  ['Tulum Peyniri', 'kg', 420, ['Süt Ürünleri', 'Kahvaltılık']],
  ['Köy Yumurtası', 'adet', 6, ['Kahvaltılık']],
  ['Kuru Fasulye', 'kg', 90, ['Kuru Gıda']],
  ['Tereyağı', 'kg', 480, ['Süt Ürünleri', 'Kahvaltılık']],
];

const CIFTLIK_ADLARI = ['Yeşil Vadi Çiftliği', 'Dağ Yamacı Bahçesi', 'Pınarbaşı Arıcılık', 'Gün Işığı Tarım', 'Çınaraltı Çiftliği'];
const ILLER = ['Bingöl', 'Muş', 'Elazığ', 'Erzurum', 'Diyarbakır'];

function verileriDoldur() {
  const db = baglan();

  // Tüm doldurma tek bir transaction içinde: yarıda hata olursa hiçbir şey eklenmez.
  // Bonus: Transaction içinde toplu INSERT, tek tek INSERT'ten çok daha hızlıdır.
  islem(db, () => {
    // Önce eski örnek verileri temizle (çocuk tablolardan başlayarak — FK sırası önemli!)
    db.exec(`
      DELETE FROM siparis_kalemi; DELETE FROM siparis; DELETE FROM fiyat_gecmisi;
      DELETE FROM urun_kategori;  DELETE FROM urun;    DELETE FROM kategori;
      DELETE FROM uretici;        DELETE FROM kullanici;
      DELETE FROM sqlite_sequence; -- AUTOINCREMENT sayaçlarını sıfırla
    `);

    // Hazır komutlar (prepared statement): "?" yerine değer güvenli şekilde konur -> SQL Injection önlenir
    const kullaniciEkle = db.prepare('INSERT INTO kullanici (kullanici_adi, eposta, rol) VALUES (?, ?, ?)');
    const ureticiEkle = db.prepare('INSERT INTO uretici (kullanici_id, ciftlik_adi, il) VALUES (?, ?, ?)');
    const kategoriEkle = db.prepare('INSERT INTO kategori (ad, aciklama) VALUES (?, ?)');
    const urunEkle = db.prepare('INSERT INTO urun (uretici_id, ad, birim, fiyat, stok) VALUES (?, ?, ?, ?, ?)');
    const urunKategoriEkle = db.prepare('INSERT INTO urun_kategori (urun_id, kategori_id) VALUES (?, ?)');
    const fiyatEkle = db.prepare('INSERT INTO fiyat_gecmisi (urun_id, fiyat, tarih) VALUES (?, ?, ?)');
    const siparisEkle = db.prepare('INSERT INTO siparis (alici_id, durum) VALUES (?, ?)');
    const kalemEkle = db.prepare('INSERT INTO siparis_kalemi (siparis_id, urun_id, miktar, birim_fiyat) VALUES (?, ?, ?, ?)');

    // 1) Kategoriler
    const kategoriId = {};
    for (const [ad, aciklama] of KATEGORILER) {
      kategoriId[ad] = Number(kategoriEkle.run(ad, aciklama).lastInsertRowid);
    }

    // 2) Yönetici + 5 üretici kullanıcı + 8 alıcı kullanıcı (hepsi sentetik)
    kullaniciEkle.run('admin01', 'admin01@ornek.test', 'admin');

    const ureticiIdleri = [];
    for (let i = 1; i <= 5; i++) {
      const kod = `uretici${String(i).padStart(2, '0')}`;
      const kId = Number(kullaniciEkle.run(kod, `${kod}@ornek.test`, 'uretici').lastInsertRowid);
      ureticiIdleri.push(Number(ureticiEkle.run(kId, CIFTLIK_ADLARI[i - 1], ILLER[i - 1]).lastInsertRowid));
    }

    const aliciIdleri = [];
    for (let i = 1; i <= 8; i++) {
      const kod = `alici${String(i).padStart(2, '0')}`;
      aliciIdleri.push(Number(kullaniciEkle.run(kod, `${kod}@ornek.test`, 'alici').lastInsertRowid));
    }

    // 3) Her üreticiye rastgele 4 ürün + kategori eşleşmeleri + 6 aylık fiyat geçmişi
    const tumUrunler = []; // { id, fiyat }
    for (const ureticiId of ureticiIdleri) {
      const secilenler = new Set();
      while (secilenler.size < 4) secilenler.add(sec(URUNLER));

      for (const [ad, birim, taban, kategoriler] of secilenler) {
        // Fiyat geçmişi: son 6 ay, taban fiyatın etrafında dalgalanır
        let fiyat = yuvarla(taban * (0.85 + rastgele() * 0.3));
        const gecmis = [];
        for (let ay = 5; ay >= 0; ay--) {
          fiyat = yuvarla(fiyat * (0.95 + rastgele() * 0.12));
          const t = new Date();
          t.setMonth(t.getMonth() - ay);
          gecmis.push([fiyat, t.toISOString().slice(0, 10)]); // "2026-05-09" biçiminde tarih
        }

        const stok = Math.floor(10 + rastgele() * 190);
        const urunId = Number(urunEkle.run(ureticiId, ad, birim, fiyat, stok).lastInsertRowid);

        for (const kAd of kategoriler) urunKategoriEkle.run(urunId, kategoriId[kAd]);

        for (const [f, tarih] of gecmis) fiyatEkle.run(urunId, f, tarih);
        tumUrunler.push({ id: urunId, fiyat });
      }
    }

    // 4) 12 sipariş, her birinde 1-3 farklı ürün
    const durumlar = ['beklemede', 'onaylandi', 'teslim_edildi', 'teslim_edildi', 'iptal'];
    for (let s = 0; s < 12; s++) {
      const siparisId = Number(siparisEkle.run(sec(aliciIdleri), sec(durumlar)).lastInsertRowid);
      const kalemler = new Set();
      const adet = 1 + Math.floor(rastgele() * 3);
      while (kalemler.size < adet) kalemler.add(sec(tumUrunler));
      for (const u of kalemler) kalemEkle.run(siparisId, u.id, 1 + Math.floor(rastgele() * 5), u.fiyat);
    }
  });

  // Özet
  const say = (t) => db.prepare(`SELECT COUNT(*) AS n FROM ${t}`).get().n;
  console.log('Sentetik veri eklendi:');
  for (const t of ['kullanici', 'uretici', 'kategori', 'urun', 'urun_kategori', 'fiyat_gecmisi', 'siparis', 'siparis_kalemi']) {
    console.log(`  ${t.padEnd(15)} ${say(t)} satır`);
  }
  db.close();
}

if (require.main === module) verileriDoldur();
module.exports = { verileriDoldur };
