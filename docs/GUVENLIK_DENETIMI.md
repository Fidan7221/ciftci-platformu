# Güvenlik ve Performans Denetimi (Hafta 11)

Bu belge, Hafta 11'de projede yapılan güvenlik gözden geçirmesinin sonucudur: her tehdit için
**ne kontrol edildi → ne bulundu → hangi önlem alındı → hangi test doğruluyor**.

## 1. Tehdit → önlem → test tablosu

| Tehdit | Durum (denetim öncesi) | Önlem | Test (`tests/test_security.py`) |
|---|---|---|---|
| **CSRF** | Flask-WTF `CSRFProtect` tüm POST formlarında açıktı | Korundu; jetonsuz POST `400` döner | `test_state_changing_requests_without_csrf_token_are_rejected` (ürün silme, sipariş iptali, ilan kapatma) |
| **XSS (depolanan)** | Jinja2 otomatik kaçış açıktı, `|safe` kullanılmıyordu | Korundu + CSP ikinci savunma hattı | `test_product_and_listing_names_are_escaped`, `test_flash_message_with_user_input_is_escaped` |
| **XSS (yansıyan)** | Arama kutusu kaçırılıyordu | Korundu | `test_reflected_search_text_is_escaped` |
| **XSS → JS'e veri** | İlan formunda Python verisi JS'e elle yazılıyordu | `tojson` filtresi | `test_prices.py` (ilan formu ipucu) |
| **Satır içi betikler** | 3 `onsubmit`, 1 `javascript:` bağlantısı, 2 nonce'suz `<script>` | `static/js/app.js` + `data-confirm`; nonce | `test_templates_contain_no_inline_event_handlers`, `test_inline_scripts_carry_the_request_nonce`, `test_nonce_is_different_on_every_request` |
| **Clickjacking** | Başlık yoktu | `X-Frame-Options: DENY`, `frame-ancestors 'none'` | `test_security_headers_on_every_response` |
| **SQL Injection** | Ham SQL yok; ORM parametreli sorgu kullanıyor | Korundu | `test_sql_injection_in_search_is_treated_as_text`, `test_sql_injection_in_login_fails` |
| **LIKE joker kötüye kullanımı** | `%` ve `_` kaçırılmıyordu (`%` tüm kayıtları getirir) | `contains_pattern()` + `ESCAPE '\'` | `test_like_wildcards_are_escaped` |
| **IDOR** (başkasının nesnesi) | Depo sorguları zaten sahibe göre filtreliyordu | Korundu; ihlal `404` döner | `test_producer_cannot_touch_another_producers_*`, `test_customer_cannot_access_another_customers_order_payment_or_cart`, `test_object_level_violations_return_404_not_403` |
| **Rol ihlali** | `@role_required` vardı | Korundu; ihlal `403` döner | `test_role_violations_return_403[...]` (7 senaryo) |
| **Toplu atama (mass assignment)** | Formlar alanları tek tek eşliyordu | Korundu; `is_verified`, `role`, `email` formdan değişmez | `test_producer_cannot_verify_self_or_set_reputation`, `test_customer_cannot_change_role_or_email_via_account_form` |
| **Kötü amaçlı dosya** | Görsel imzası kontrol ediliyordu | Korundu (SVG reddedilir) | `test_svg_upload_is_rejected` |
| **Brute force (hesap)** | Sınırsız deneme | 15 dk'da 5 hatalı giriş → kilit (`429`) | `test_account_locks_after_repeated_failed_logins`, `test_successful_login_resets_failure_counter` |
| **Brute force (IP) / spam** | Sınır yoktu | IP başına: giriş 20/dk, kayıt 10/saat, sepete ekleme 30/dk | `test_login_attempts_are_limited_per_ip`, `test_registration_spam_is_limited`, `test_cart_add_is_rate_limited` |
| **Kullanıcı keşfi (timing)** | Olmayan e-posta hızlı yanıt veriyordu | Sahte hash ile eşit süre | `test_unknown_email_costs_the_same_password_check` |
| **Oturum çalma** | Varsayılan koruma | `session_protection = "strong"` | `test_session_protection_is_strong`, `test_tampered_session_user_id_is_treated_as_anonymous` |
| **Zayıf gizli anahtar** | Üretimde varsayılan anahtarla açılabiliyordu | Üretimde <32 karakter veya varsayılan anahtar → başlamaz | `test_production_refuses_default_or_short_secret_key` |

## 2. 403 mü, 404 mü?

- **Rol ihlali → 403 Forbidden.** Müşteri `/uretici/panel` adresine girerse sayfanın var olduğu zaten herkesçe bilinir;
  "yetkin yok" demek bilgi sızdırmaz.
- **Nesne ihlali (IDOR) → 404 Not Found.** Veli, Ali'nin `/uretici/urunler/17/duzenle` adresini denerse 403 dönmek
  "17 numaralı ürün var ama senin değil" demektir; saldırgan id'leri tarayarak hangi kayıtların var olduğunu öğrenir.
  Bu yüzden sorgu baştan `WHERE id = :id AND producer_id = :benim_id` şeklinde yazılır, kayıt bulunamaz ve 404 döner.

## 3. Hız sınırının bilinen sınırlamaları

- Sayaçlar bellektedir (`app/utils/rate_limit.py`). Tek süreçli geliştirme sunucusu için yeterlidir; birden fazla
  gunicorn işçisi kullanılırsa her işçinin ayrı sayacı olur → üretimde **Redis** gibi ortak bir depo gerekir.
- Uygulama Nginx gibi bir ters vekil arkasındaysa `request.remote_addr` vekilin adresi olur; bu durumda
  `werkzeug.middleware.proxy_fix.ProxyFix` eklenmelidir (aksi hâlde herkes aynı IP sayılır).
- Hesap kilitleme, saldırganın başkasının hesabını bilerek kilitlemesine (DoS) izin verir. Bu yüzden kilit kalıcı değil
  15 dakikalıktır ve doğru parola ile girişte sayaç sıfırlanır.

## 4. Performans

### İndeksler

| Tablo | İndeks | Hangi sorgu için |
|---|---|---|
| `listings` | `(status, created_at)` | Pazar: aktif ilanlar, en yeniden eskiye |
| `orders` | `(customer_id, created_at)` | "Siparişlerim" listesi |
| `market_prices` | `(category_id, price_date)` | Kategori fiyat serisi (grafik ve yapay zekâ) |
| `price_predictions` | `(product_id, model_name, target_date)` | Tahmin upsert araması |
| `products` | `category_id` | Kategoriye göre filtre, kategori başına ürün sayısı |
| `categories` | `parent_id` | Alt kategoriler |
| `users` | `role_id` | Rol bazlı sayımlar |
| `cart_items`, `order_items` | `listing_id` | İlan silinirken/kapatılırken bağlı kalemler |
| `reviews` | `customer_id` | Müşterinin yorumları |

Bileşik indeksler **soldan önek** kuralıyla çalışır: `(status, created_at)` indeksi `WHERE status = ?` sorgusunda
da kullanılır, ama yalnızca `created_at` ile yapılan sorguda kullanılmaz.

### N+1 düzeltmeleri

| Sayfa | Sorun | Çözüm |
|---|---|---|
| Pazar (`/pazar/`) | Her ilan için ürün ve üretici ayrı sorgu | Zaten JOIN edilen tablolar için `contains_eager` |
| Siparişlerim / üretici siparişleri / yönetici | Her sipariş için kalemler, ilan, ürün, müşteri, ödeme | `ORDER_DETAILS` (`selectinload` + `joinedload`) |
| Sepet | Her kalem için ilan → ürün → üretici | Zincirleme `selectinload` |
| Yönetici kategorileri | `category.products|length` her satırda tüm ürünleri yüklüyordu | Tek `GROUP BY` sayım sorgusu |
| Fiyatlar | Her satır için önceki gün ortalaması ve tahmin | `previous_averages()` ve `forecasts_for_categories()` tek sorgu |
| Her istek | `current_user.role` ve `producer_profile` ayrı sorgular | `load_user` içinde `joinedload` |

**Doğrulama:** Geliştirme ve test ortamında her yanıtta `X-Query-Count` başlığı bulunur. Testler aynı sayfayı az ve çok
kayıtla açıp sorgu sayısının **değişmediğini** doğrular (`test_*_query_count_does_not_grow*`). N+1 olsaydı sayı kayıt
sayısıyla birlikte artardı.
