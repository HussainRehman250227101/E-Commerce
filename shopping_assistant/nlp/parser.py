"""DistilBERT intent classification, with a safe rule-based fallback."""

import os
import re
from functools import lru_cache
from pathlib import Path

INTENTS = {
    "search_products", "cheapest_product", "top_rated_products",
    "budget_search", "compare_products", "clarify",
}
ASSISTANT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_MODEL_PATH = ASSISTANT_DIR / "artifacts" / "intent_model"

BRANDS = {
    "apple": ("apple", "iphone", "ipad"),
    "samsung": ("samsung", "galaxy"),
    "google": ("google", "pixel"),
    "xiaomi": ("xiaomi", "redmi", "poco"),
    "oneplus": ("oneplus", "one plus"),
    "oppo": ("oppo",), "vivo": ("vivo",), "huawei": ("huawei",),
    "infinix": ("infinix",), "tecno": ("tecno",),
}
MODEL_PATTERNS = (
    r"\biphone(?:\s+\d{1,2})?(?:\s+(?:pro|max|plus|mini|ultra)){0,2}\b",
    r"\bgalaxy(?:\s+[aszm]\d{1,2})?(?:\s+(?:fe|plus|ultra|pro|fold|flip)){0,2}\b",
    r"\bpixel(?:\s+\d{1,2})?(?:\s+(?:pro|xl|a)){0,2}\b",
    r"\bredmi(?:\s+note)?(?:\s+\d{1,2})?(?:\s+(?:pro|plus))?\b",
    r"\boneplus(?:\s+\d{1,2})?(?:\s+(?:pro|r))?\b",
)
MAX_PRICE = re.compile(
    r"\b(?:under|below|less than|up to|maximum(?: of)?|max(?:imum)?(?: of)?)\s*"
    r"(?:rs\.?|pkr|rupees?|\$)?\s*([\d,]+(?:\.\d+)?)", re.I
)
MIN_PRICE = re.compile(
    r"\b(?:over|above|more than|at least|minimum of)\s*"
    r"(?:rs\.?|pkr|rupees?|\$)?\s*([\d,]+(?:\.\d+)?)", re.I
)
PRICE_RANGE = re.compile(
    r"\bbetween\s+(?:rs\.?|pkr|rupees?|\$)?\s*([\d,]+(?:\.\d+)?)"
    r"\s+and\s+(?:rs\.?|pkr|rupees?|\$)?\s*([\d,]+(?:\.\d+)?)", re.I
)
RATING_PATTERNS = (
    re.compile(r"\b(?:rating|rated)\s*(?:of|above|over|at least)?\s*(\d(?:\.\d)?)", re.I),
    re.compile(r"\b(?:above|over|at least)\s*(\d(?:\.\d)?)\s*stars?\b", re.I),
    re.compile(r"\b(\d(?:\.\d)?)\s*stars?\b", re.I),
)


def _number(value):
    try:
        return float(value.replace(",", ""))
    except (AttributeError, TypeError, ValueError):
        return None


def _fallback_intent(text):
    lower = text.lower()
    if re.search(r"\b(compare|comparison|versus|vs\.?|differences between)\b", lower):
        return "compare_products"
    if re.search(r"\b(cheapest|least expensive|lowest price|lowest priced|costs the least|most affordable)\b", lower):
        return "cheapest_product"
    if re.search(r"\b(top rated|highest rated|best rated|highly rated|best reviewed|highest rating)\b", lower):
        return "top_rated_products"
    if re.search(r"\b(under|below|less than|up to|budget|price range|maximum budget|within my budget|between \d)\b", lower):
        return "budget_search"
    if re.search(r"\b(which one|that product|tell me more|what do you mean|help me decide|narrow down)\b", lower):
        return "clarify"
    return "search_products"


@lru_cache(maxsize=1)
def _load_intent_pipeline():
    configured = os.getenv("SHOPPING_INTENT_MODEL_PATH")
    model_path = Path(configured) if configured else DEFAULT_MODEL_PATH
    if not model_path.exists():
        return None
    try:
        from transformers import pipeline
        return pipeline("text-classification", model=str(model_path), tokenizer=str(model_path), device=-1)
    except (ImportError, OSError, ValueError):
        return None


def predict_intent(text):
    fallback = _fallback_intent(text)
    classifier = _load_intent_pipeline()
    if classifier is None:
        return fallback
    try:
        prediction = classifier(text[:1000], truncation=True, max_length=128)[0]
        label = prediction.get("label", "")
        if label in INTENTS and float(prediction.get("score", 0)) >= 0.45:
            return label
    except (KeyError, TypeError, ValueError, RuntimeError):
        pass
    return fallback


def extract_slots(text):
    lower = text.lower()
    slots = {
        "product_type": None, "brand": None, "model_keyword": None,
        "min_price": None, "max_price": None, "min_rating": None,
        "price_preference": None, "rating_preference": None,
        "in_stock_only": True, "result_limit": 5, "sort_by": None,
    }

    for pattern in MODEL_PATTERNS:
        match = re.search(pattern, lower, re.I)
        if match:
            slots["model_keyword"] = re.sub(r"\s+", " ", match.group(0)).strip()
            break

    for brand, aliases in BRANDS.items():
        if any(re.search(r"\b" + re.escape(alias) + r"\b", lower) for alias in aliases):
            slots["brand"] = brand.title() if brand != "xiaomi" else "Xiaomi"
            break

    if re.search(r"\b(phone|phones|mobile|mobiles|smartphone|smartphones|iphone|galaxy|pixel|redmi|oneplus)\b", lower):
        slots["product_type"] = "phone"

    range_match = PRICE_RANGE.search(text)
    if range_match:
        slots["min_price"] = _number(range_match.group(1))
        slots["max_price"] = _number(range_match.group(2))
    else:
        max_match = MAX_PRICE.search(text)
        min_match = MIN_PRICE.search(text)
        if max_match:
            slots["max_price"] = _number(max_match.group(1))
        if min_match and not max_match:
            # Avoid treating "above 4.5 stars" as a minimum product price.
            suffix = text[min_match.end():]
            if not re.match(r"\s*stars?\b", suffix, re.I):
                slots["min_price"] = _number(min_match.group(1))

    for pattern in RATING_PATTERNS:
        match = pattern.search(text)
        if match:
            value = _number(match.group(1))
            if value is not None and 0 <= value <= 5:
                slots["min_rating"] = value
                break
    if slots["min_rating"] is None and re.search(r"\b(highly rated|top rated|best rated|best reviewed|excellent ratings?)\b", lower):
        slots["min_rating"] = 4.0

    if re.search(r"\b(cheapest|least expensive|lowest priced|lowest price|most affordable)\b", lower):
        slots["price_preference"] = "lowest"
        slots["sort_by"] = "price_ascending"
    elif re.search(r"\b(most expensive|highest price|premium price)\b", lower):
        slots["price_preference"] = "highest"
        slots["sort_by"] = "price_descending"

    if re.search(r"\b(top rated|highest rated|best rated|best reviewed|highest rating)\b", lower):
        slots["rating_preference"] = "highest"
        if slots["sort_by"] is None:
            slots["sort_by"] = "rating_descending"

    if re.search(r"\b(include out of stock|include unavailable|out of stock is fine)\b", lower):
        slots["in_stock_only"] = False

    limit_match = re.search(r"\b(?:top|first|show me|give me)\s+(\d{1,2})\b", lower)
    if limit_match:
        slots["result_limit"] = max(1, min(int(limit_match.group(1)), 10))
    return slots


def parse_message(text):
    return {"intent": predict_intent(text), **extract_slots(text)}
