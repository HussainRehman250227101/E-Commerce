"""Tag-aware Django ORM filtering for parsed shopping requests."""

from decimal import Decimal, InvalidOperation
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from store.models import Product
from tags.models import TaggedItem

BRAND_ALIASES = {
    "apple": ("apple", "iphone", "ipad", "watch", "airpods"),
    "samsung": ("samsung", "galaxy"),
    "google": ("google", "pixel"),
    "xiaomi": ("xiaomi", "redmi", "poco"),
    "oneplus": ("oneplus", "one plus"),
    "oppo": ("oppo",), "vivo": ("vivo",),
    "huawei": ("huawei",), "infinix": ("infinix",), "tecno": ("tecno",),
}

CATEGORY_TERMS = {
    "phone": ("phone", "mobile", "smartphone", "iphone", "galaxy", "pixel", "redmi", "oneplus"),
    "watch": ("watch", "smartwatch"),
    "tablet": ("tablet", "ipad"),
    "laptop": ("laptop", "notebook"),
    "headphones": ("headphones", "headphone", "earbuds", "earphones", "airpods"),
    "charger": ("charger", "charging adapter", "power adapter"),
    "case": ("phone case", "mobile case", "phone cover", "mobile cover"),
}


def _tagged_product_ids(terms):
    """Return product IDs with a tag label containing any supplied term."""
    terms = tuple(term for term in terms if term)
    if not terms:
        return []
    content_type = ContentType.objects.get_for_model(Product)
    tag_query = Q()
    for term in terms:
        tag_query |= Q(tag__label__icontains=term)
    return TaggedItem.objects.filter(
        content_type=content_type
    ).filter(tag_query).values_list("object_id", flat=True)


def _term_query(terms):
    query = Q()
    for term in terms:
        if term:
            query |= (
                Q(title__icontains=term)
                | Q(description__icontains=term)
                | Q(collection__title__icontains=term)
                | Q(id__in=_tagged_product_ids([term]))
            )
    return query


def _category_query(category):
    return _term_query(CATEGORY_TERMS.get(category, ()))


def _decimal(value):
    if value is None:
        return None
    try:
        result = Decimal(str(value))
        return result if result >= 0 else None
    except (InvalidOperation, TypeError, ValueError):
        return None


def build_product_queryset(parsed):
    products = Product.objects.select_related("collection").prefetch_related("images").all()
    model_keyword = parsed.get("model_keyword")
    brand = (parsed.get("brand") or "").lower()

    product_type = parsed.get("product_type")

    # Apply the requested category first. This is a strict filter: if the
    # store has no watches, Apple Watch searches return no products rather
    # than falling back to an iPhone with the same brand tag.
    if product_type in CATEGORY_TERMS:
        products = products.filter(_category_query(product_type))

    if model_keyword:
        products = products.filter(_term_query([model_keyword]))
    elif brand in BRAND_ALIASES:
        products = products.filter(_term_query(BRAND_ALIASES[brand]))

    min_price = _decimal(parsed.get("min_price"))
    max_price = _decimal(parsed.get("max_price"))
    min_rating = _decimal(parsed.get("min_rating"))

    if min_price is not None:
        products = products.filter(unit_price__gte=min_price)
    if max_price is not None:
        products = products.filter(unit_price__lte=max_price)
    if min_rating is not None and min_rating <= 5:
        products = products.filter(rating__gte=min_rating)
    if parsed.get("in_stock_only", True):
        products = products.filter(inventory__gt=0)
    return products
