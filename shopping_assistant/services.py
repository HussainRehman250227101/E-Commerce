"""Orchestrate parsing, catalog search and response formatting."""

from .catalog import build_product_queryset
from .nlp.parser import parse_message
from .ranking import rank_products


def _serialize_product(product):
    image_url = None
    try:
        image_url = product.images.all()[0].image.url
    except (IndexError, ValueError, AttributeError):
        pass
    return {
        "id": product.id,
        "title": product.title,
        "price": float(product.unit_price),
        "rating": float(product.rating),
        "image": image_url,
        "url": f"/products/{product.id}",
        "in_stock": product.inventory > 0,
    }


def answer_message(message):
    parsed = parse_message(message)
    if parsed["intent"] == "clarify" and not any(parsed.get(k) for k in ("brand", "model_keyword", "product_type", "min_price", "max_price")):
        return {
            "message": "What type of product are you looking for? A brand or budget would help me narrow it down.",
            "intent": parsed["intent"],
            "products": [],
            "filters_applied": {},
            "ranking_strategy": "not_applicable",
        }

    queryset = build_product_queryset(parsed)
    if parsed.get("sort_by") == "price_ascending":
        queryset = queryset.order_by("unit_price", "-rating")
    elif parsed.get("sort_by") == "price_descending":
        queryset = queryset.order_by("-unit_price", "-rating")
    elif parsed.get("sort_by") == "rating_descending":
        queryset = queryset.order_by("-rating", "unit_price")
    else:
        queryset = queryset.order_by("-rating", "unit_price")

    candidates = list(queryset[:200])
    limit = max(1, min(int(parsed.get("result_limit") or 5), 10))
    ranked, strategy = rank_products(candidates, parsed, limit)

    if not ranked:
        message_text = "I couldn't find matching in-stock products. Try relaxing your budget or rating requirement."
    elif parsed["intent"] == "cheapest_product":
        message_text = f"I found {len(ranked)} of the lowest-priced matching products."
    elif parsed["intent"] == "top_rated_products":
        message_text = f"Here are {len(ranked)} of the highest-rated matching products."
    elif parsed["intent"] == "compare_products":
        message_text = f"Here are {len(ranked)} matching products you can compare."
    else:
        message_text = f"I found {len(ranked)} matching products for your search."

    filters = {
        key: parsed[key] for key in
        ("brand", "model_keyword", "product_type", "min_price", "max_price", "min_rating", "in_stock_only", "sort_by")
        if parsed.get(key) not in (None, False, "")
    }
    return {
        "message": message_text,
        "intent": parsed["intent"],
        "products": [_serialize_product(product) for product in ranked],
        "filters_applied": filters,
        "ranking_strategy": strategy,
    }
