# ER Diyagramı (Hafta 3-4, Hafta 11 itibarıyla güncel)

Veritabanında **14 tablo** vardır. Aşağıdaki diyagram `app/models/` içindeki modellerden çıkarılmıştır.
GitHub ve VS Code (Markdown Preview Mermaid Support eklentisiyle) Mermaid kodunu doğrudan çizer;
aynı diyagramın resmi: [`er_diyagrami.png`](er_diyagrami.png).

![ER diyagramı](er_diyagrami.png)

## Gösterim

| Sembol | Anlamı |
|---|---|
| `||--o{` | bire-çok (bir rolün sıfır veya çok kullanıcısı) |
| `||--o|` | bire-bir, isteğe bağlı (her kullanıcının en fazla bir üretici profili) |
| `||--|{` | bire-çok, en az bir (siparişte en az bir kalem olmalı) |
| PK / FK / UK | birincil anahtar / yabancı anahtar / benzersiz |

```mermaid
erDiagram
    ROLES ||--o{ USERS : "sahiptir"
    USERS ||--o| PRODUCER_PROFILES : "üretici ise"
    USERS ||--o| CARTS : "sepeti"
    USERS ||--o{ ORDERS : "verir"
    USERS ||--o{ REVIEWS : "yazar"
    PRODUCER_PROFILES ||--o{ PRODUCTS : "üretir"
    PRODUCER_PROFILES ||--o{ ORDER_ITEMS : "satar"
    PRODUCER_PROFILES ||--o{ REVIEWS : "alır"
    CATEGORIES ||--o{ CATEGORIES : "alt kategori"
    CATEGORIES ||--o{ PRODUCTS : "içerir"
    CATEGORIES ||--o{ MARKET_PRICES : "hal fiyatı"
    PRODUCTS ||--o{ LISTINGS : "ilana çıkar"
    PRODUCTS ||--o{ PRICE_PREDICTIONS : "tahmin"
    CARTS ||--o{ CART_ITEMS : "içerir"
    LISTINGS ||--o{ CART_ITEMS : "sepette"
    LISTINGS ||--o{ ORDER_ITEMS : "satılır"
    ORDERS ||--|{ ORDER_ITEMS : "içerir"
    ORDERS ||--o| PAYMENTS : "ödenir"
    ORDER_ITEMS ||--o| REVIEWS : "değerlendirilir"

    ROLES {
        int id PK
        string name UK "customer, producer, admin"
        string description
    }
    USERS {
        int id PK
        int role_id FK
        string full_name
        string email UK
        string password_hash
        string phone
        string city
        string address
        bool is_active_account
        datetime created_at
    }
    PRODUCER_PROFILES {
        int id PK
        int user_id FK,UK
        string farm_name
        string region
        text description
        string tax_number
        bool is_verified
        float reputation_score
        int review_count
    }
    CATEGORIES {
        int id PK
        string name
        string slug UK
        int parent_id FK "kendine bağlı"
    }
    PRODUCTS {
        int id PK
        int producer_id FK
        int category_id FK
        string name
        string unit "kg, adet, kasa..."
        decimal stock_quantity
        text description
        bool is_organic
        string image_path
        bool is_active
    }
    LISTINGS {
        int id PK
        int product_id FK
        string title
        decimal price
        decimal stock_quantity
        decimal min_order_quantity
        date start_date
        date end_date
        string status "active, sold_out, closed"
    }
    CARTS {
        int id PK
        int user_id FK,UK
    }
    CART_ITEMS {
        int id PK
        int cart_id FK
        int listing_id FK
        decimal quantity
    }
    ORDERS {
        int id PK
        int customer_id FK
        decimal total_amount
        string status "pending, paid, shipped, delivered, cancelled"
        string shipping_address
        string note
        datetime created_at
    }
    ORDER_ITEMS {
        int id PK
        int order_id FK
        int listing_id FK
        int producer_id FK
        decimal quantity
        decimal unit_price "sipariş anındaki fiyat"
    }
    PAYMENTS {
        int id PK
        int order_id FK,UK
        string provider
        string transaction_ref UK
        decimal amount
        string status
        string idempotency_key
        int attempt_count
        string card_last4 "yalnızca son 4 hane"
        datetime paid_at
        string refund_ref
    }
    REVIEWS {
        int id PK
        int order_item_id FK,UK
        int customer_id FK
        int producer_id FK
        int rating "1-5"
        text comment
        bool is_visible
    }
    MARKET_PRICES {
        int id PK
        int category_id FK
        string product_name
        string source
        string unit
        decimal min_price
        decimal max_price
        decimal avg_price
        date price_date
    }
    PRICE_PREDICTIONS {
        int id PK
        int product_id FK
        string model_name
        date target_date
        decimal predicted_price
        string trend "up, down, stable"
        float confidence
        decimal suggested_price
        string action
        float backtest_mape
    }
```

## Önemli tasarım kararları

- **Rol ayrı tablo:** `roles` → `users` (1-N). Yetki kontrolü `@role_required` ile rol adına göre yapılır.
- **Üretici profili ayrı tablo:** Yalnızca üreticilerin çiftlik bilgisi vardır; `users` tablosu boş sütunlarla şişmez (1-1, `user_id` UNIQUE).
- **Ürün ≠ İlan:** Ürün üreticinin elindeki malı (toplam stok), ilan ise satışa çıkarılan kısmını (fiyat, satış stoğu, tarih) tutar.
  Aynı ürün farklı fiyatlarla birden çok kez ilana çıkabilir.
- **Kategori kendine bağlı:** `parent_id` ile ağaç yapısı (Sebze → Domates).
- **Sipariş kalemi fiyatı kopyalar:** `order_items.unit_price` sipariş anındaki fiyattır; ilan fiyatı sonradan değişse de eski sipariş bozulmaz.
  `producer_id` da kaleme yazılır; böylece üretici "bana gelen siparişler"i uzun JOIN zinciri olmadan bulur.
- **Bir siparişin en fazla bir ödemesi:** `payments.order_id` UNIQUE; çift çekime karşı `idempotency_key`. Kart numarasının yalnızca son 4 hanesi saklanır.
- **Değerlendirme kaleme bağlı:** `reviews.order_item_id` UNIQUE → aynı alışveriş iki kez puanlanamaz; yalnızca teslim edilen sipariş değerlendirilebilir.
- **Hal fiyatı kategoriye bağlı:** `market_prices` tablosunda (`product_name`, `source`, `price_date`) üçlüsü benzersizdir; yapay zekâ tahminleri `price_predictions` tablosundadır.
- Her tabloda `id`, `created_at`, `updated_at` vardır (`BaseModel`); diyagram kalabalık olmasın diye çoğunda gösterilmedi.
