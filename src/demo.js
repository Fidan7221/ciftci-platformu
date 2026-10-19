// =====================================================================
// demo.js — CRUD işlemlerini ve kısıtların ÇALIŞTIĞINI gösteren test/demonstrasyon
// Hocaya gösterirken:  npm run demo
// =====================================================================
const { baglan } = require('./db');
const { UrunRepository, siparisOlustur } = require('./urunRepository');

const db = baglan();
const repo = new UrunRepository(db);

const baslik = (metin) => console.log(`\n${'='.repeat(60)}\n${metin}\n${'='.repeat(60)}`);

// Kısıt testi yardımcısı: işlem HATA VERMELİ. Hata verirse kısıt çalışıyor demektir.
function kisitTesti(aciklama, fonksiyon) {
  try {
    fonksiyon();
    console.log(`  ❌ BAŞARISIZ — hata bekleniyordu ama işlem geçti: ${aciklama}`);
  } catch (hata) {
    console.log(`  ✅ Engellendi: ${aciklama}\n     SQLite mesajı: ${hata.message}`);
  }
}

// ------------------------------------------------------------------ CREATE
baslik('1) CREATE — Yeni ürün ekle');
const yeniId = repo.ekle({
  ureticiId: 1,
  ad: 'Organik Ayva',
  birim: 'kg',
  fiyat: 55,
  stok: 40,
  kategoriIdleri: [2, 5], // Meyve + Kahvaltılık (N-N ilişki)
});
console.log(`Eklenen ürün id: ${yeniId}`);

// ------------------------------------------------------------------ READ
baslik('2) READ — Tek ürün getir (JOIN ile üretici + kategoriler)');
console.table([repo.getir(yeniId)]);

baslik('2b) READ — "Kahvaltılık" kategorisindeki ürünler (kategoriId = 5)');
console.table(repo.listele({ kategoriId: 5 }));

// ------------------------------------------------------------------ UPDATE
baslik('3) UPDATE — Fiyatı 55 → 62, stok 40 → 35');
console.log('Değişen satır sayısı:', repo.guncelle(yeniId, { fiyat: 62, stok: 35 }));
console.table([repo.getir(yeniId)]);
console.log('Fiyat geçmişi (fiyat takip özelliği):');
console.table(repo.fiyatGecmisi(yeniId));

// ------------------------------------------------------------------ DELETE
baslik('4) DELETE — Ürünü sil (CASCADE ile kategori eşleşmesi ve fiyat geçmişi de silinir)');
const say = (sql, ...p) => db.prepare(sql).get(...p).n;
console.log('Silmeden önce urun_kategori satırı:', say('SELECT COUNT(*) n FROM urun_kategori WHERE urun_id=?', yeniId));
console.log('Silinen satır sayısı:', repo.sil(yeniId));
console.log('Sildikten sonra urun_kategori satırı:', say('SELECT COUNT(*) n FROM urun_kategori WHERE urun_id=?', yeniId));
console.log('Sildikten sonra fiyat_gecmisi satırı:', say('SELECT COUNT(*) n FROM fiyat_gecmisi WHERE urun_id=?', yeniId));
console.log('getir() sonucu:', repo.getir(yeniId)); // undefined

// ------------------------------------------------------------------ KISITLAR
baslik('5) KISIT TESTLERİ — Bunların HEPSİ hata vermeli');

kisitTesti('FOREIGN KEY: Var olmayan üreticiye (id=999) ürün eklenemez', () =>
  repo.ekle({ ureticiId: 999, ad: 'Hayalet Ürün', birim: 'kg', fiyat: 10 }));

kisitTesti('CHECK: Negatif fiyat girilemez', () =>
  repo.ekle({ ureticiId: 1, ad: 'Bedava Domates', birim: 'kg', fiyat: -5 }));

kisitTesti('CHECK: Geçersiz birim ("ton") girilemez', () =>
  repo.ekle({ ureticiId: 1, ad: 'Ton Patates', birim: 'ton', fiyat: 10 }));

kisitTesti('UNIQUE: Aynı e-posta ile ikinci kullanıcı açılamaz', () =>
  db.prepare("INSERT INTO kullanici (kullanici_adi, eposta) VALUES ('yeni', 'alici01@ornek.test')").run());

kisitTesti('NOT NULL: Ürün adı boş (NULL) olamaz', () =>
  db.prepare("INSERT INTO urun (uretici_id, ad, birim, fiyat) VALUES (1, NULL, 'kg', 10)").run());

kisitTesti('PRIMARY KEY (N-N): Aynı ürün aynı kategoriye 2. kez bağlanamaz', () => {
  const { urun_id, kategori_id } = db.prepare('SELECT urun_id, kategori_id FROM urun_kategori LIMIT 1').get();
  db.prepare('INSERT INTO urun_kategori (urun_id, kategori_id) VALUES (?, ?)').run(urun_id, kategori_id);
});

kisitTesti('ON DELETE RESTRICT: Ürünü olan üretici silinemez', () =>
  db.prepare('DELETE FROM uretici WHERE id = 1').run());

kisitTesti('ON DELETE RESTRICT: Satılmış (siparişte geçen) ürün silinemez', () => {
  const { urun_id } = db.prepare('SELECT urun_id FROM siparis_kalemi LIMIT 1').get();
  repo.sil(urun_id);
});

// ------------------------------------------------------------------ TRANSACTION
baslik('6) TRANSACTION — Stok yetmezse sipariş TAMAMEN geri alınır');
const urun = db.prepare('SELECT id, ad, stok FROM urun WHERE aktif = 1 ORDER BY id LIMIT 2').all();
const siparisSayisiOnce = say('SELECT COUNT(*) n FROM siparis');
console.log(`Önce: "${urun[0].ad}" stok=${urun[0].stok}, "${urun[1].ad}" stok=${urun[1].stok}, sipariş sayısı=${siparisSayisiOnce}`);

kisitTesti(`1. ürün 1 adet (yeterli) + 2. ürün ${urun[1].stok + 1000} adet (YETERSİZ) siparişi`, () =>
  siparisOlustur(db, 7, [
    { urunId: urun[0].id, miktar: 1 },
    { urunId: urun[1].id, miktar: urun[1].stok + 1000 },
  ]));

const sonra = db.prepare('SELECT stok FROM urun WHERE id = ?');
console.log(`Sonra: "${urun[0].ad}" stok=${sonra.get(urun[0].id).stok} (DEĞİŞMEDİ — ROLLBACK çalıştı), sipariş sayısı=${say('SELECT COUNT(*) n FROM siparis')}`);

const basariliId = siparisOlustur(db, 7, [{ urunId: urun[0].id, miktar: 2 }]);
console.log(`Geçerli sipariş oluşturuldu: id=${basariliId}, "${urun[0].ad}" yeni stok=${sonra.get(urun[0].id).stok}`);

db.close();
console.log('\nDemo tamamlandı.');
