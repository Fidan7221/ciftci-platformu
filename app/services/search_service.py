"""Pazar yeri arama ve filtreleme iş mantığı (Hafta 12).

Akış:  rota  ->  MarketFilter.from_args(request.args)  ->  search_market()  ->  ListingRepository
Filtre nesnesi doğrulanmış gelir; burada yalnızca veritabanına bağlı çözümlemeler yapılır:
- Seçilen kategori, alt kategorileriyle birlikte id listesine çevrilir.
- İl / ilçe seçimi, üreticilerin serbest yazdığı ham bölge metinlerine çevrilir.
"""
from flask import current_app

from app.repositories.listing_repository import ListingRepository
from app.repositories.product_repository import CategoryRepository
from app.utils.market_filter import SORT_OPTIONS, MarketFilter, RegionIndex


def region_index():
    return RegionIndex.build(ListingRepository.available_regions())


def _category_ids(category):
    return [category.id] + [child.id for child in category.children]


def search_market(filters: MarketFilter, page=1, regions_index=None):
    """Filtreye uyan, satıştaki ilanlar (sayfalı). (pagination, filtre, kategori) döner.

    Var olmayan bir kategori id'si gelirse (?kategori=9999) filtre yok sayılır; boş sayfa yerine
    tüm ilanlar gösterilir ve etiketlerde görünmez.
    """
    category = CategoryRepository.get_by_id(filters.category_id) if filters.category_id else None
    if filters.category_id and category is None:
        filters = filters.without("category_id")
    regions = None
    if filters.il:
        regions = (regions_index or region_index()).raw_regions(filters.il, filters.ilce or None)
    pagination = ListingRepository.search_available(
        filters,
        category_ids=_category_ids(category) if category else None,
        regions=regions,
        page=max(page, 1),
        per_page=current_app.config.get("ITEMS_PER_PAGE", 12),
    )
    return pagination, filters, category


def market_page(args):
    """Pazar sayfasının ihtiyaç duyduğu her şey tek sözlükte (rota ince kalsın).

    args: request.args (werkzeug MultiDict)
    """
    regions = region_index()
    pagination, filters, category = search_market(
        MarketFilter.from_args(args), args.get("sayfa", 1, type=int), regions)
    low, high = ListingRepository.available_price_range()
    return {
        "filters": filters,
        "pagination": pagination,
        "chips": filters.chips(category.name if category else None),
        "region_options": regions.options(),
        "sort_options": {key: label for key, label in SORT_OPTIONS.items()
                         if key != "ilgi" or filters.tokens},
        "price_hint": (low, high),
    }
