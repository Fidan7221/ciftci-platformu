erDiagram
ROLES ||--o{ USERS : "rol tanımlar"
USERS ||--|| PRODUCER_PROFILES : "üretici detayları"
USERS ||--|| CARTS : "sepeti vardır"
USERS ||--o{ ORDERS : "sipariş verir"

    PRODUCER_PROFILES ||--o{ PRODUCTS : "ürün üretir"
    PRODUCER_PROFILES ||--o{ LISTINGS : "ilan açar"
    PRODUCER_PROFILES ||--o{ REVIEWS : "yorum alır"

    CATEGORIES ||--o{ PRODUCTS : "ürünleri kategoriler"
    CATEGORIES ||--o{ CATEGORIES : "üst/alt kategori"
    CATEGORIES ||--o{ MARKET_PRICES : "hal/piyasa fiyatları"

    PRODUCTS ||--o{ LISTINGS : "satış ilanları"
    PRODUCTS ||--o{ PRICE_PREDICTIONS : "yapay zeka tahminleri"

    CARTS ||--o{ CART_ITEMS : "sepetteki ürünler"
    LISTINGS ||--o{ CART_ITEMS : "ilandan sepete"

    ORDERS ||--o{ ORDER_ITEMS : "sipariş kalemleri"
    ORDERS ||--|| PAYMENTS : "ödeme kaydı"
    LISTINGS ||--o{ ORDER_ITEMS : "satın alınan ilan"
    ORDER_ITEMS ||--o| REVIEWS : "satın alınan ürüne yorum"

    USERS {
        int id PK
        int role_id FK
        string full_name
        string email UK
        string password_hash
        string phone
        string city
        boolean is_active
    }

    PRODUCER_PROFILES {
        int id PK
        int user_id FK
        string farm_name
        string region
        text description
        float reputation_score
        boolean is_verified
    }

    CATEGORIES {
        int id PK
        int parent_id FK
        string name
    }

    PRODUCTS {
        int id PK
        int producer_id FK
        int category_id FK
        string name
        string unit
        text description
    }

    LISTINGS {
        int id PK
        int product_id FK
        decimal price
        int stock_quantity
        date start_date
        date end_date
        string status
    }

    ORDERS {
        int id PK
        int customer_id FK
        decimal total_amount
        string status
        text shipping_address
    }

    PAYMENTS {
        int id PK
        int order_id FK
        string provider
        decimal amount
        string status
    }

    PRICE_PREDICTIONS {
        int id PK
        int product_id FK
        decimal predicted_price
        date target_date
        string trend
    }
