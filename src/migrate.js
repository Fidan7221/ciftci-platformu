// =====================================================================
// migrate.js — Basit migration (göç) aracı
//
// Mantık:
// 1) "schema_migrations" adında bir kayıt tablosu tutulur.
// 2) migrations/ klasöründeki .sql dosyaları isim sırasıyla (001, 002, ...) okunur.
// 3) Daha önce çalıştırılmış olan dosya ATLANIR, yeni olan çalıştırılır.
// 4) Her migration bir TRANSACTION içinde çalışır: yarısı başarılı olup
//    veritabanı bozuk kalmaz; hata olursa o migration tamamen geri alınır.
//
// Çalıştırma:  npm run migrate
// =====================================================================
const fs = require('node:fs');
const path = require('node:path');
const { baglan, islem } = require('./db');

const MIGRATION_KLASORU = path.join(__dirname, '..', 'migrations');

function migrationlariCalistir() {
  const db = baglan();

  // Hangi migration'ların uygulandığını tutan tablo (yoksa oluştur)
  db.exec(`
    CREATE TABLE IF NOT EXISTS schema_migrations (
      dosya_adi      TEXT PRIMARY KEY,
      uygulama_tarihi TEXT NOT NULL DEFAULT (datetime('now'))
    );
  `);

  // Daha önce uygulanmış olanları bir kümeye (Set) al
  const uygulananlar = new Set(
    db.prepare('SELECT dosya_adi FROM schema_migrations').all().map((s) => s.dosya_adi)
  );

  // Klasördeki .sql dosyalarını isim sırasına göre al (001 önce, 002 sonra)
  const dosyalar = fs
    .readdirSync(MIGRATION_KLASORU)
    .filter((d) => d.endsWith('.sql'))
    .sort();

  let yeniSayisi = 0;
  for (const dosya of dosyalar) {
    if (uygulananlar.has(dosya)) {
      console.log(`  ⏭  Atlandı (zaten uygulanmış): ${dosya}`);
      continue;
    }

    const sql = fs.readFileSync(path.join(MIGRATION_KLASORU, dosya), 'utf8');

    // Migration + kayıt işlemi aynı transaction'da: ikisi birlikte olur ya da hiç olmaz
    islem(db, () => {
      db.exec(sql);
      db.prepare('INSERT INTO schema_migrations (dosya_adi) VALUES (?)').run(dosya);
    });

    console.log(`  ✅ Uygulandı: ${dosya}`);
    yeniSayisi++;
  }

  console.log(yeniSayisi === 0 ? 'Veritabanı zaten güncel.' : `${yeniSayisi} migration uygulandı.`);
  db.close();
}

// Bu dosya doğrudan çalıştırıldıysa (node src/migrate.js) migration'ları uygula
if (require.main === module) {
  migrationlariCalistir();
}

module.exports = { migrationlariCalistir };
