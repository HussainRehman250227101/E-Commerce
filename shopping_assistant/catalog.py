"""Safe Django ORM product filtering for parsed shopping requests."""

from decimal import Decimal, InvalidOperation
from django.db.models import Q
from store.models import Product

BRAND_ALIASES = {
    "apple": ("apple", "iphone"), "samsung": ("samsung", "galaxy"),
    "google": ("google", "pixel"), "xiaomi": ("xiaomi", "redmi", "poco"),
    "oneplus": ("oneplus", "one plus"), "oppo": ("oppo",), "vivo": ("vivo",),
    "huawei": ("huawei",), "infinix": ("infinix",), "tecno": ("tecno",),
}
PHONE_TERMS = ("phone", "mobile", "smartphone", "iphone", "galaxy", "pixel", "redmi", "oneplus")


def _term_query(terms):
    query = Q()
    for term in terms:
        if term:
            query |= Q(title__icontains=term) | Q(description__icontains=term) | Q(collection__title__icontains=term)
    return query


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

    if model_keyword:
        products = products.filter(_term_query([model_keyword]))
    elif brand in BRAND_ALIASES:
        products = products.filter(_term_query(BRAND_ALIASES[brand]))
    elif parsed.get("product_type") == "phone":
        products = products.filter(_term_query(PHONE_TERMS))

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
