// =====================================================================
// urunRepository.js — VERİ ERİŞİM KATMANI (Data Access Layer / Repository)
//
// Amaç: SQL komutlarını tek bir yerde toplamak. Uygulamanın geri kalanı
// (ileride yazılacak web API, ekranlar) SQL bilmeden bu fonksiyonları çağırır.
//
// CRUD = Create (Ekle) / Read (Listele-Getir) / Update (Güncelle) / Delete (Sil)
// Bu komutların hepsi DML'dir (Data Manipulation Language): INSERT, SELECT, UPDATE, DELETE
//
// GÜVENLİK: Tüm sorgularda "?" veya ":isim" yer tutucuları kullanılır.
// Kullanıcıdan gelen değer ASLA SQL metnine string birleştirme ile eklenmez.
// Böylece SQL Injection saldırısı engellenir.
// =====================================================================
const { islem } = require('./db');

class UrunRepository {
  constructor(db) {
    this.db = db;
  }

  // -------------------------------------------------------------------
  // C — CREATE (Ekle)
  // Ürünü ekler, kategorilerine bağlar ve ilk fiyatı geçmişe yazar.
  // 3 farklı tabloya yazıldığı için TRANSACTION kullanılır:
  // kategori eşleşmesi hata verirse ürün de eklenmemiş olur.
  // -------------------------------------------------------------------
  ekle({ ureticiId, ad, birim, fiyat, stok = 0, kategoriIdleri = [] }) {
    return islem(this.db, () => {
      const sonuc = this.db
        .prepare(
          `INSERT INTO urun (uretici_id, ad, birim, fiyat, stok)
           VALUES (:ureticiId, :ad, :birim, :fiyat, :stok)`
        )
        .run({ ureticiId, ad, birim, fiyat, stok });

      const urunId = Number(sonuc.lastInsertRowid); // Veritabanının verdiği yeni id

      const kategoriBagla = this.db.prepare('INSERT INTO urun_kategori (urun_id, kategori_id) VALUES (?, ?)');
      for (const kategoriId of kategoriIdleri) kategoriBagla.run(urunId, kategoriId);

      this.db.prepare('INSERT INTO fiyat_gecmisi (urun_id, fiyat) VALUES (?, ?)').run(urunId, fiyat);

      return urunId;
    });
  }

  // -------------------------------------------------------------------
  // R — READ (Tek kayıt getir)
  // -------------------------------------------------------------------
  getir(id) {
    return this.db
      .prepare(
        `SELECT u.id, u.ad, u.birim, u.fiyat, u.stok, u.aktif,
                ur.ciftlik_adi, ur.il,
                GROUP_CONCAT(k.ad, ', ') AS kategoriler
         FROM urun u
         JOIN uretici ur           ON ur.id = u.uretici_id      -- 1-N ilişki üzerinden birleştirme
         LEFT JOIN urun_kategori uk ON uk.urun_id = u.id        -- N-N ilişki: önce ara tabloya
         LEFT JOIN kategori k       ON k.id = uk.kategori_id    -- sonra kategoriye git
         WHERE u.id = ?
         GROUP BY u.id`
      )
      .get(id); // Bulunamazsa undefined döner
  }

  // -------------------------------------------------------------------
  // R — READ (Listele, isteğe bağlı filtreli)
  // -------------------------------------------------------------------
  listele({ ureticiId = null, kategoriId = null, aramaMetni = null } = {}) {
    return this.db
      .prepare(
        `SELECT u.id, u.ad, u.birim, u.fiyat, u.stok, ur.ciftlik_adi
         FROM urun u
         JOIN uretici ur ON ur.id = u.uretici_id
         WHERE u.aktif = 1
           AND (:ureticiId  IS NULL OR u.uretici_id = :ureticiId)
           AND (:aramaMetni IS NULL OR u.ad LIKE '%' || :aramaMetni || '%')
           AND (:kategoriId IS NULL OR EXISTS (
                 SELECT 1 FROM urun_kategori uk
                 WHERE uk.urun_id = u.id AND uk.kategori_id = :kategoriId))
         ORDER BY u.ad, u.fiyat`
      )
      .all({ ureticiId, kategoriId, aramaMetni });
  }

  // -------------------------------------------------------------------
  // U — UPDATE (Güncelle)
  // Sadece gönderilen alanlar değişir (COALESCE: yeni değer NULL ise eskisini koru).
  // Fiyat değiştiyse fiyat_gecmisi'ne yeni satır eklenir -> "fiyat takip" özelliği.
  // İki tabloya yazıldığı için yine TRANSACTION.
  // -------------------------------------------------------------------
  guncelle(id, { ad = null, fiyat = null, stok = null, aktif = null } = {}) {
    return islem(this.db, () => {
      const eski = this.db.prepare('SELECT fiyat FROM urun WHERE id = ?').get(id);
      if (!eski) return 0; // Böyle bir ürün yok

      const sonuc = this.db
        .prepare(
          `UPDATE urun
           SET ad    = COALESCE(:ad, ad),
               fiyat = COALESCE(:fiyat, fiyat),
               stok  = COALESCE(:stok, stok),
               aktif = COALESCE(:aktif, aktif),
               guncelleme_tarihi = datetime('now')
           WHERE id = :id`
        )
        .run({ id, ad, fiyat, stok, aktif });

      if (fiyat !== null && fiyat !== eski.fiyat) {
        this.db.prepare('INSERT INTO fiyat_gecmisi (urun_id, fiyat) VALUES (?, ?)').run(id, fiyat);
      }
      return Number(sonuc.changes); // Kaç satır değişti (0 veya 1)
    });
  }

  // -------------------------------------------------------------------
  // D — DELETE (Sil)
  // urun_kategori ve fiyat_gecmisi satırları ON DELETE CASCADE ile otomatik silinir.
  // Ürün daha önce satıldıysa siparis_kalemi'ndeki ON DELETE RESTRICT silmeyi ENGELLER
  // (sipariş geçmişi bozulmasın). O durumda ürün "pasif" yapılmalıdır.
  // -------------------------------------------------------------------
  sil(id) {
    const sonuc = this.db.prepare('DELETE FROM urun WHERE id = ?').run(id);
    return Number(sonuc.changes);
  }

  // -------------------------------------------------------------------
  // Fiyat takip sorgusu: bir ürünün fiyat geçmişi (idx_fiyat_gecmisi_urun_tarih indeksini kullanır)
  // -------------------------------------------------------------------
  fiyatGecmisi(urunId) {
    return this.db
      .prepare('SELECT tarih, fiyat FROM fiyat_gecmisi WHERE urun_id = ? ORDER BY tarih')
      .all(urunId);
  }
}

// =====================================================================
// Sipariş oluşturma — TRANSACTION'ın en klasik örneği
// Adımlar: (1) sipariş başlığı ekle  (2) her kalem için stoktan düş  (3) kalemi ekle
// Stok yetmezse CHECK(stok >= 0) kısıtı hata verir -> HER ŞEY geri alınır.
// Transaction olmasaydı: sipariş açılmış, bazı stoklar düşmüş ama sipariş yarım kalmış olurdu.
// =====================================================================
function siparisOlustur(db, aliciId, kalemler /* [{ urunId, miktar }] */) {
  return islem(db, () => {
    const siparisId = Number(
      db.prepare('INSERT INTO siparis (alici_id) VALUES (?)').run(aliciId).lastInsertRowid
    );
    for (const { urunId, miktar } of kalemler) {
      const urun = db.prepare('SELECT fiyat FROM urun WHERE id = ? AND aktif = 1').get(urunId);
      if (!urun) throw new Error(`Ürün bulunamadı veya satışta değil: ${urunId}`);

      db.prepare('UPDATE urun SET stok = stok - ? WHERE id = ?').run(miktar, urunId);
      db.prepare(
        'INSERT INTO siparis_kalemi (siparis_id, urun_id, miktar, birim_fiyat) VALUES (?, ?, ?, ?)'
      ).run(siparisId, urunId, miktar, urun.fiyat);
    }
    return siparisId;
  });
}

module.exports = { UrunRepository, siparisOlustur };
