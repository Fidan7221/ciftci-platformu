// sifirla.js — Veritabanı dosyasını siler (her şeye sıfırdan başlamak için)
// Çalıştırma:  npm run sifirla   ardından   npm run migrate && npm run seed
const fs = require('node:fs');
const { DB_YOLU } = require('./db');

if (fs.existsSync(DB_YOLU)) {
  fs.unlinkSync(DB_YOLU);
  console.log('ciftci.db silindi.');
} else {
  console.log('Silinecek veritabanı yok.');
}
