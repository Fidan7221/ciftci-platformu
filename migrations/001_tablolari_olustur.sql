-- =====================================================================
-- MIGRATION 001: Tabloları oluştur
-- Proje: Çiftçi Doğrudan Satış ve Fiyat Takip Platformu
-- Bu dosyadaki komutların hepsi DDL'dir (Data Definition Language).
-- DDL tabloların YAPISINI tanımlar: CREATE, ALTER, DROP
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1) KULLANICI: Sisteme giriş yapan herkes (alıcı, üretici, yönetici)
-- ---------------------------------------------------------------------
CREATE TABLE kullanici (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,      -- Birincil anahtar (PK): her satırı benzersiz tanımlar
    kullanici_adi    TEXT    NOT NULL UNIQUE,                -- UNIQUE: aynı kullanıcı adı iki kez olamaz
    eposta           TEXT    NOT NULL UNIQUE,                -- UNIQUE kısıtı SQLite'ta otomatik indeks oluşturur
    rol              TEXT    NOT NULL DEFAULT 'alici'
                     CHECK (rol IN ('alici', 'uretici', 'admin')), -- CHECK: sadece bu 3 değer kabul edilir
    olusturma_tarihi TEXT    NOT NULL DEFAULT (datetime('now'))
    -- NOT: Telefon, TC kimlik no, adres gibi alanlar BİLEREK eklenmedi.
    -- KVKK "veri minimizasyonu" ilkesi: amaç için gerekmeyen kişisel veri toplanmaz.
);

-- ---------------------------------------------------------------------
-- 2) URETICI: Ürün satan çiftçinin profil bilgisi
--    İlişki: KULLANICI 1 --- 0..1 URETICI (bire-bir)
-- ---------------------------------------------------------------------
CREATE TABLE uretici (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    kullanici_id  INTEGER NOT NULL UNIQUE,                   -- UNIQUE olduğu için ilişki 1-1 olur
    ciftlik_adi   TEXT    NOT NULL,
    il            TEXT    NOT NULL,
    -- ELLE YAZILAN İLİŞKİ VE KISIT #1 (yabancı anahtar):
    -- kullanici_id sütunu, kullanici tablosundaki id'yi göstermek ZORUNDADIR.
    -- Var olmayan bir kullanıcıya üretici profili eklenemez.
    -- ON DELETE CASCADE: kullanıcı silinirse onun üretici profili de otomatik silinir.
    CONSTRAINT fk_uretici_kullanici
        FOREIGN KEY (kullanici_id) REFERENCES kullanici(id)
        ON DELETE CASCADE
);

-- ---------------------------------------------------------------------
-- 3) KATEGORI: Sebze, Meyve, Süt Ürünleri ...
-- ---------------------------------------------------------------------
CREATE TABLE kategori (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    ad       TEXT    NOT NULL UNIQUE,                        -- Aynı isimli iki kategori olamaz
    aciklama TEXT
);

-- ---------------------------------------------------------------------
-- 4) URUN: Üreticinin satışa çıkardığı ürün
--    İlişki: URETICI 1 --- N URUN (bire-çok)
-- ---------------------------------------------------------------------
CREATE TABLE urun (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    uretici_id        INTEGER NOT NULL,
    ad                TEXT    NOT NULL CHECK (length(trim(ad)) > 0), -- Boş isim engellenir
    birim             TEXT    NOT NULL
                      CHECK (birim IN ('kg', 'adet', 'litre', 'demet')),
    fiyat             REAL    NOT NULL CHECK (fiyat > 0),     -- ELLE YAZILAN KISIT #2: fiyat 0 veya negatif olamaz
    stok              INTEGER NOT NULL DEFAULT 0 CHECK (stok >= 0), -- Stok eksiye düşemez
    aktif             INTEGER NOT NULL DEFAULT 1 CHECK (aktif IN (0, 1)), -- SQLite'ta boolean = 0/1
    olusturma_tarihi  TEXT    NOT NULL DEFAULT (datetime('now')),
    guncelleme_tarihi TEXT    NOT NULL DEFAULT (datetime('now')),
    -- ON DELETE RESTRICT: Ürünü olan bir üretici SİLİNEMEZ.
    -- Önce ürünleri silinmeli/taşınmalı. Böylece "sahipsiz ürün" (yetim kayıt) oluşmaz.
    CONSTRAINT fk_urun_uretici
        FOREIGN KEY (uretici_id) REFERENCES uretici(id)
        ON DELETE RESTRICT,
    -- Aynı üretici aynı isimde iki ürün açamaz (bileşik UNIQUE kısıt)
    CONSTRAINT uq_urun_uretici_ad UNIQUE (uretici_id, ad)
);

-- ---------------------------------------------------------------------
-- 5) URUN_KATEGORI: Ürün <-> Kategori arası ÇOKA-ÇOK (N-N) ilişki
--    Bir ürün birden çok kategoride olabilir (Bal: "Arı Ürünleri" + "Kahvaltılık")
--    Bir kategoride birden çok ürün olabilir.
--    N-N ilişki doğrudan kurulamaz -> ARA TABLO (junction table) kullanılır.
-- ---------------------------------------------------------------------
CREATE TABLE urun_kategori (
    urun_id     INTEGER NOT NULL,
    kategori_id INTEGER NOT NULL,
    -- Bileşik birincil anahtar: aynı ürün aynı kategoriye 2 kez eklenemez
    PRIMARY KEY (urun_id, kategori_id),
    FOREIGN KEY (urun_id)     REFERENCES urun(id)     ON DELETE CASCADE,  -- Ürün silinirse eşleşmesi de silinir
    FOREIGN KEY (kategori_id) REFERENCES kategori(id) ON DELETE RESTRICT  -- İçinde ürün olan kategori silinemez
);

-- ---------------------------------------------------------------------
-- 6) FIYAT_GECMISI: Platformun "fiyat takip" özelliği
--    Ürünün fiyatı her değiştiğinde buraya bir satır eklenir.
--    İlişki: URUN 1 --- N FIYAT_GECMISI
-- ---------------------------------------------------------------------
CREATE TABLE fiyat_gecmisi (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    urun_id INTEGER NOT NULL,
    fiyat   REAL    NOT NULL CHECK (fiyat > 0),
    tarih   TEXT    NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (urun_id) REFERENCES urun(id) ON DELETE CASCADE
);

-- ---------------------------------------------------------------------
-- 7) SIPARIS: Alıcının verdiği sipariş (başlık bilgisi)
--    İlişki: KULLANICI(alıcı) 1 --- N SIPARIS
-- ---------------------------------------------------------------------
CREATE TABLE siparis (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    alici_id INTEGER NOT NULL,
    tarih    TEXT    NOT NULL DEFAULT (datetime('now')),
    durum    TEXT    NOT NULL DEFAULT 'beklemede'
             CHECK (durum IN ('beklemede', 'onaylandi', 'teslim_edildi', 'iptal')),
    FOREIGN KEY (alici_id) REFERENCES kullanici(id) ON DELETE RESTRICT -- Siparişi olan kullanıcı silinemez
);

-- ---------------------------------------------------------------------
-- 8) SIPARIS_KALEMI: Sipariş <-> Ürün arası N-N ilişki (EK ALANLI ara tablo)
--    Ara tabloda ilişkinin kendine ait bilgileri de tutulur: miktar, birim_fiyat
--    birim_fiyat burada AYRICA saklanır çünkü ürünün fiyatı sonradan değişebilir;
--    eski siparişin tutarı değişmemelidir.
-- ---------------------------------------------------------------------
CREATE TABLE siparis_kalemi (
    siparis_id  INTEGER NOT NULL,
    urun_id     INTEGER NOT NULL,
    miktar      REAL    NOT NULL CHECK (miktar > 0),
    birim_fiyat REAL    NOT NULL CHECK (birim_fiyat > 0),
    PRIMARY KEY (siparis_id, urun_id),
    FOREIGN KEY (siparis_id) REFERENCES siparis(id) ON DELETE CASCADE,
    FOREIGN KEY (urun_id)    REFERENCES urun(id)    ON DELETE RESTRICT -- Satılmış ürün silinemez (pasif yapılır)
);
