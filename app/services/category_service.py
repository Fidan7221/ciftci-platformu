"""Kategori yönetimi iş mantığı (Hafta 6). Kategorileri yalnızca yönetici düzenler.

Kurallar:
- Kategori ağacı en fazla 2 seviyelidir: Üst kategori > Alt kategori.
- Ürünü ya da alt kategorisi olan kategori silinemez.
- slug (URL adı) benzersizdir ve boş bırakılırsa addan üretilir.
"""
import re

from app.models import Category
from app.repositories.product_repository import CategoryRepository
from app.services.errors import ServiceError

_TR_MAP = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")


def slugify(text):
    """'Bal ve Arı Ürünleri' -> 'bal-ve-ari-urunleri'"""
    text = (text or "").translate(_TR_MAP).lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def parent_choices(exclude_id=None):
    """Üst kategori açılır listesi. Yalnızca 1. seviye kategoriler üst olabilir."""
    choices = [(0, "— Üst kategori yok (ana kategori) —")]
    choices += [(c.id, c.name) for c in CategoryRepository.get_top_level() if c.id != exclude_id]
    return choices


def product_category_choices():
    """Ürün formundaki gruplu açılır liste: {"Sebze": [(id, "Domates"), ...]}"""
    groups = {}
    standalone = []
    for parent in CategoryRepository.get_top_level():
        if parent.children:
            groups[parent.name] = [(c.id, c.name) for c in sorted(parent.children, key=lambda c: c.name)]
        else:
            standalone.append((parent.id, parent.name))
    if standalone:
        groups["Diğer"] = standalone
    return groups


def category_tree():
    """Yönetici listesi için: [(üst kategori, [alt kategoriler]), ...]"""
    tree = []
    for parent in CategoryRepository.get_top_level():
        children = sorted(parent.children, key=lambda c: c.name)
        tree.append((parent, children))
    return tree


def _validate(name, slug, parent_id, category=None):
    name = (name or "").strip()
    slug = slugify(slug) if slug else slugify(name)
    if not slug:
        raise ServiceError("Geçerli bir kategori adı girin.", field="name")

    existing = CategoryRepository.get_by_slug(slug)
    if existing is not None and existing is not category:
        raise ServiceError(f"'{slug}' adresi başka bir kategoride kullanılıyor.", field="slug")

    parent = None
    if parent_id:
        parent = CategoryRepository.get_by_id(parent_id)
        if parent is None or parent.parent_id is not None:
            raise ServiceError("Yalnızca ana kategoriler üst kategori olarak seçilebilir.", field="parent_id")
        if category is not None and parent.id == category.id:
            raise ServiceError("Kategori kendisinin üst kategorisi olamaz.", field="parent_id")
        if category is not None and category.children:
            raise ServiceError("Alt kategorileri olan bir kategori başka bir kategorinin altına taşınamaz.",
                               field="parent_id")
    return name, slug, parent


def create_category(name, slug=None, parent_id=None):
    name, slug, parent = _validate(name, slug, parent_id)
    category = Category(name=name, slug=slug, parent=parent)
    CategoryRepository.add(category)
    CategoryRepository.commit()
    return category


def update_category(category, name, slug=None, parent_id=None):
    name, slug, parent = _validate(name, slug, parent_id, category)
    category.name = name
    category.slug = slug
    category.parent = parent
    CategoryRepository.commit()
    return category


def delete_category(category):
    if category.children:
        raise ServiceError("Önce bu kategorinin alt kategorilerini silin veya taşıyın.")
    if CategoryRepository.product_count(category.id) > 0:
        raise ServiceError("Bu kategoride ürünler var; silinemez.")
    CategoryRepository.delete(category)
    CategoryRepository.commit()
