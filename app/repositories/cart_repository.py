"""Sepet sorguları (Hafta 7)."""
from sqlalchemy import func
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.models import Cart, CartItem, Listing, Product
from app.repositories.base_repository import BaseRepository


class CartRepository(BaseRepository):
    model = Cart

    @staticmethod
    def get_by_user_id(user_id):
        # Hafta 11: Sepet sayfası her kalem için ilan, ürün ve üreticiyi kullanır
        return db.session.execute(
            db.select(Cart).filter_by(user_id=user_id).options(
                selectinload(Cart.items).selectinload(CartItem.listing)
                .selectinload(Listing.product).selectinload(Product.producer))
        ).scalar_one_or_none()

    @staticmethod
    def get_item(cart_id, listing_id):
        return db.session.execute(
            db.select(CartItem).filter_by(cart_id=cart_id, listing_id=listing_id)
        ).scalar_one_or_none()

    @staticmethod
    def get_item_for_user(item_id, user_id):
        """Kalemi yalnızca bu kullanıcının sepetindeyse döndürür."""
        return db.session.execute(
            db.select(CartItem).join(CartItem.cart)
            .where(CartItem.id == item_id, Cart.user_id == user_id)
        ).scalar_one_or_none()

    @staticmethod
    def item_count(user_id):
        return db.session.execute(
            db.select(func.count(CartItem.id)).join(CartItem.cart).where(Cart.user_id == user_id)
        ).scalar()
