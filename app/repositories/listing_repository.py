"""İlan sorguları (Hafta 7; gelişmiş arama ve filtreleme Hafta 12)."""
from datetime import date

from sqlalchemy import case, func, or_
from sqlalchemy.orm import contains_eager

from app.extensions import db
from app.models import Category, Listing, ListingStatus, ProducerProfile, Product
from app.repositories.base_repository import LIKE_ESCAPE, BaseRepository, contains_pattern


def _available_conditions():
    """Müşteriye gösterilecek ilanların SQL koşulları (Listing.is_available ile aynı kural)."""
    today = date.today()
    return (
        Listing.status == ListingStatus.ACTIVE,
        Listing.stock_quantity > 0,
        Listing.start_date <= today,
        or_(Listing.end_date.is_(None), Listing.end_date >= today),
        Product.is_active.is_(True),
    )


# Hafta 12: Arama kutusundaki her kelime bu sütunlardan EN AZ BİRİNDE geçmelidir.
# Sütunlar tr_fold() ile katlanır (Türkçe büyük/küçük harf + ç/ğ/ı/ö/ş/ü duyarsız arama).
def _search_columns():
    return (Listing.title, Product.name, Product.description, ProducerProfile.farm_name,
            ProducerProfile.region, Category.name)


def _token_condition(token):
    pattern = contains_pattern(token)
    return or_(*(func.tr_fold(column).like(pattern, escape=LIKE_ESCAPE) for column in _search_columns()))


def _relevance(tokens):
    """"En ilgili" sıralaması için basit puan: başlıkta/ürün adında geçmek çiftlik adında geçmekten değerli."""
    score = 0
    for token in tokens:
        pattern = contains_pattern(token)
        score = score + case((func.tr_fold(Listing.title).like(pattern, escape=LIKE_ESCAPE), 3), else_=0) \
                      + case((func.tr_fold(Product.name).like(pattern, escape=LIKE_ESCAPE), 2), else_=0) \
                      + case((func.tr_fold(ProducerProfile.farm_name).like(pattern, escape=LIKE_ESCAPE), 1), else_=0)
    return score


_NEWEST = (Listing.created_at.desc(), Listing.id.desc())

# Her sıralamanın sonunda id vardır: eşit fiyatlı ilanlar sayfalar arasında yer değiştirmesin
# (kararlı sıralama olmazsa bir ilan hem 1. hem 2. sayfada görünebilir ya da hiç görünmeyebilir).
_SORTS = {
    "yeni": lambda tokens: _NEWEST,
    "fiyat_artan": lambda tokens: (Listing.price.asc(), Listing.id.desc()),
    "fiyat_azalan": lambda tokens: (Listing.price.desc(), Listing.id.desc()),
    "degerlendirme": lambda tokens: (ProducerProfile.review_count.desc(),
                                     ProducerProfile.reputation_score.desc(), *_NEWEST),
    "puan": lambda tokens: (ProducerProfile.reputation_score.desc(),
                            ProducerProfile.review_count.desc(), *_NEWEST),
    "ilgi": lambda tokens: (_relevance(tokens).desc(), *_NEWEST) if tokens else _NEWEST,
}


class ListingRepository(BaseRepository):
    model = Listing

    @staticmethod
    def get_for_producer(listing_id, producer_id):
        return db.session.execute(
            db.select(Listing).join(Listing.product)
            .where(Listing.id == listing_id, Product.producer_id == producer_id)
        ).scalar_one_or_none()

    @staticmethod
    def paginate_for_producer(producer_id, status=None, page=1, per_page=12, tokens=(), sort="yeni"):
        stmt = (db.select(Listing).join(Listing.product)
                .options(contains_eager(Listing.product))  # Hafta 11: ürün zaten JOIN'de; ayrı sorgu yok
                .where(Product.producer_id == producer_id))
        if status:
            stmt = stmt.where(Listing.status == status)
        for token in tokens:  # Hafta 12: üretici kendi ilanlarında başlık / ürün adına göre arar
            pattern = contains_pattern(token)
            stmt = stmt.where(or_(func.tr_fold(Listing.title).like(pattern, escape=LIKE_ESCAPE),
                                  func.tr_fold(Product.name).like(pattern, escape=LIKE_ESCAPE)))
        order = {"fiyat_artan": (Listing.price.asc(), Listing.id.desc()),
                 "fiyat_azalan": (Listing.price.desc(), Listing.id.desc()),
                 "stok": (Listing.stock_quantity.asc(), Listing.id.desc())}.get(sort, _NEWEST)
        stmt = stmt.order_by(*order)
        return db.paginate(stmt, page=page, per_page=per_page, error_out=False)

    @staticmethod
    def search_available(filters, category_ids=None, regions=None, page=1, per_page=12):
        """Pazar yeri araması (Hafta 12). Tüm koşullar AND ile birleşir.

        filters  : MarketFilter (app/utils/market_filter.py)
        category_ids: seçilen kategori + alt kategorileri (None = hepsi)
        regions  : filtreye uyan ham bölge metinleri (None = filtre yok, [] = hiçbir şey eşleşmez)
        """
        stmt = (db.select(Listing).join(Listing.product).join(Product.producer).join(Product.category)
                # Hafta 11: JOIN'lenen ürün ve üretici nesnelere doldurulur. Olmasaydı her kart için
                # listing.product ve product.producer ayrı ayrı sorgulanırdı (12 ilan = 24 ek sorgu).
                .options(contains_eager(Listing.product).contains_eager(Product.producer))
                .where(*_available_conditions()))

        tokens = filters.tokens
        for token in tokens:
            stmt = stmt.where(_token_condition(token))
        if category_ids:
            stmt = stmt.where(Product.category_id.in_(category_ids))
        if regions is not None:
            stmt = stmt.where(ProducerProfile.region.in_(regions))
        if filters.min_price is not None:
            stmt = stmt.where(Listing.price >= filters.min_price)
        if filters.max_price is not None:
            stmt = stmt.where(Listing.price <= filters.max_price)
        if filters.organic:
            stmt = stmt.where(Product.is_organic.is_(True))
        if filters.verified:
            stmt = stmt.where(ProducerProfile.is_verified.is_(True))

        order = _SORTS.get(filters.sort, _SORTS["yeni"])(tokens)
        stmt = stmt.order_by(*order)
        return db.paginate(stmt, page=page, per_page=per_page, error_out=False)

    @staticmethod
    def available_regions():
        """Satışta ilanı olan üreticilerin bölgeleri (filtrede boş seçenek çıkmasın)."""
        return db.session.execute(
            db.select(ProducerProfile.region).distinct()
            .join(ProducerProfile.products).join(Product.listings)
            .where(*_available_conditions())
        ).scalars().all()

    @staticmethod
    def available_price_range():
        """Satıştaki ilanların en düşük / en yüksek birim fiyatı (fiyat kutularında ipucu)."""
        return db.session.execute(
            db.select(func.min(Listing.price), func.max(Listing.price))
            .join(Listing.product).where(*_available_conditions())
        ).one()

    @staticmethod
    def active_reserved_quantity(product_id, exclude_listing_id=None):
        """Ürünün AKTİF ilanlarına ayrılmış toplam miktar."""
        stmt = (db.select(func.coalesce(func.sum(Listing.stock_quantity), 0))
                .where(Listing.product_id == product_id, Listing.status == ListingStatus.ACTIVE))
        if exclude_listing_id:
            stmt = stmt.where(Listing.id != exclude_listing_id)
        return db.session.execute(stmt).scalar()
