-- =====================================================================
-- MIGRATION 002: İndeksler
-- İndeks = kitabın sonundaki "dizin" gibidir. Veritabanı tüm tabloyu
-- satır satır taramak (full table scan) yerine doğrudan ilgili satırlara gider.
-- Bedeli: ek disk alanı + INSERT/UPDATE/DELETE biraz yavaşlar
-- (çünkü indeksin de güncellenmesi gerekir). Bu yüzden HER SÜTUNA EKLENMEZ.
-- =====================================================================

-- EKLENDİ: urun.uretici_id
-- Neden: "Bu üreticinin ürünlerini listele" en sık yapılan sorgu.
-- Ayrıca SQLite yabancı anahtar sütunlarına otomatik indeks KOYMAZ;
-- indeks olmazsa üretici silinirken RESTRICT kontrolü tüm urun tablosunu tarar.
CREATE INDEX idx_urun_uretici ON urun(uretici_id);

-- EKLENDİ: urun.ad
-- Neden: Alıcılar ürünleri isimle arar ("Domates" ara).
CREATE INDEX idx_urun_ad ON urun(ad);

-- EKLENDİ: urun_kategori.kategori_id
-- Neden: PK (urun_id, kategori_id) sırasıyla tanımlı; bu PK indeksi
-- "ürünün kategorileri" sorgusunu hızlandırır ama "kategorideki ürünler"
-- sorgusunu hızlandırmaz (bileşik indeks soldan başlayarak kullanılır).
-- O yüzden ters yön için ayrı indeks gerekir.
CREATE INDEX idx_urun_kategori_kategori ON urun_kategori(kategori_id);

-- EKLENDİ: fiyat_gecmisi(urun_id, tarih) — BİLEŞİK İNDEKS
-- Neden: Fiyat takip ekranı "X ürününün fiyatlarını tarihe göre sırala" sorgusu yapar.
-- İki sütun birlikte hem filtrelemeyi (WHERE urun_id) hem sıralamayı (ORDER BY tarih) karşılar.
CREATE INDEX idx_fiyat_gecmisi_urun_tarih ON fiyat_gecmisi(urun_id, tarih);

-- EKLENDİ: siparis.alici_id  ("Siparişlerim" ekranı)
CREATE INDEX idx_siparis_alici ON siparis(alici_id);

-- EKLENDİ: siparis_kalemi.urun_id  (ürün silinirken RESTRICT kontrolü + "bu ürün kaç kez satıldı")
CREATE INDEX idx_siparis_kalemi_urun ON siparis_kalemi(urun_id);

-- ---------------------------------------------------------------------
-- BİLEREK EKLENMEYEN İNDEKSLER (sınavda sorulursa):
-- * kullanici.eposta, kullanici.kullanici_adi, kategori.ad:
--     UNIQUE kısıtı zaten otomatik indeks oluşturur, tekrar eklemek israftır.
-- * siparis.durum, urun.aktif, urun.birim:
--     Çok az farklı değer alır (düşük seçicilik / low cardinality).
--     Satırların yarısı zaten aynı değerdeyse indeks neredeyse fayda sağlamaz.
-- * kategori tablosu: çok küçük (10-20 satır), tam tarama zaten anlık.
-- ---------------------------------------------------------------------
