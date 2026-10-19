// =====================================================================
// db.js — Veritabanı bağlantısı (tek bir yerden açılır, her dosya bunu kullanır)
// Node.js 22.13+ içinde gelen yerleşik "node:sqlite" modülünü kullanıyoruz.
// Ekstra paket kurmaya (npm install) gerek yok.
// =====================================================================
const { DatabaseSync } = require('node:sqlite');
const path = require('node:path');

// Veritabanı dosyası proje klasöründe "ciftci.db" adıyla oluşur
const DB_YOLU = path.join(__dirname, '..', 'ciftci.db');

function baglan() {
  const db = new DatabaseSync(DB_YOLU);

  // ÇOK ÖNEMLİ: SQLite'ta yabancı anahtar kontrolü VARSAYILAN OLARAK KAPALIDIR!
  // Bu satır olmazsa FOREIGN KEY kısıtları hiç çalışmaz.
  // Her bağlantı açılışında tekrar açılması gerekir.
  db.exec('PRAGMA foreign_keys = ON;');

  return db;
}

// İşlem (transaction) yardımcısı:
// Verilen fonksiyonun içindeki TÜM SQL komutları ya hep birlikte başarılı olur (COMMIT)
// ya da biri hata verirse hepsi geri alınır (ROLLBACK). "Ya hep ya hiç."
function islem(db, fonksiyon) {
  db.exec('BEGIN TRANSACTION;');
  try {
    const sonuc = fonksiyon();
    db.exec('COMMIT;');
    return sonuc;
  } catch (hata) {
    db.exec('ROLLBACK;');
    throw hata; // Hatayı çağırana ilet ki ne olduğunu görebilsin
  }
}

module.exports = { baglan, islem, DB_YOLU };
