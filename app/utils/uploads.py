"""Ürün görseli kaydetme ve silme (Hafta 6).

Güvenlik önlemleri:
1. Dosya adı kullanıcıdan alınmaz; uuid ile rastgele ad verilir
   (aynı ad çakışması ve "../../app.py" gibi yol saldırıları önlenir).
2. Uzantı kontrolü tek başına yetmez; dosyanın ilk baytlarına (imza / magic bytes)
   bakılarak gerçekten resim olup olmadığı doğrulanır.
3. Boyut sınırı config.py içindeki MAX_CONTENT_LENGTH (5 MB) ile uygulanır.
"""
import os
import uuid

PRODUCT_SUBFOLDER = "products"

# Dosya türlerinin başlangıç imzaları
_SIGNATURES = {
    "png": lambda head: head.startswith(b"\x89PNG\r\n\x1a\n"),
    "jpg": lambda head: head.startswith(b"\xff\xd8\xff"),
    "jpeg": lambda head: head.startswith(b"\xff\xd8\xff"),
    "webp": lambda head: head[:4] == b"RIFF" and head[8:12] == b"WEBP",
}


def get_extension(filename):
    return filename.rsplit(".", 1)[-1].lower() if "." in (filename or "") else ""


def is_real_image(file_storage):
    """Dosyanın içeriği, uzantısının söylediği resim türüyle eşleşiyor mu?"""
    check = _SIGNATURES.get(get_extension(file_storage.filename))
    if check is None:
        return False
    head = file_storage.stream.read(16)
    file_storage.stream.seek(0)  # Okuma imlecini başa al; yoksa kaydedilen dosya eksik olur
    return check(head)


def save_product_image(file_storage, upload_root):
    """Görseli kaydeder ve veri tabanına yazılacak göreli yolu döndürür: "products/<uuid>.png" """
    folder = os.path.join(upload_root, PRODUCT_SUBFOLDER)
    os.makedirs(folder, exist_ok=True)

    filename = f"{uuid.uuid4().hex}.{get_extension(file_storage.filename)}"
    file_storage.save(os.path.join(folder, filename))
    return f"{PRODUCT_SUBFOLDER}/{filename}"


def delete_product_image(relative_path, upload_root):
    """Görseli diskten siler. Yol dışarıdan değiştirilmiş olsa bile klasör dışına çıkamaz."""
    if not relative_path:
        return
    safe_name = os.path.basename(relative_path)
    full_path = os.path.join(upload_root, PRODUCT_SUBFOLDER, safe_name)
    if os.path.isfile(full_path):
        os.remove(full_path)
