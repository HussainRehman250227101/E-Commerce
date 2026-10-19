"""Explicit sorts plus optional XGBoost; use a simple baseline until trained."""

import os
from functools import lru_cache
from pathlib import Path

FEATURES = ["price", "rating", "price_rank", "rating_rank", "text_relevance", "in_stock", "brand_match", "budget_fit"]
APP_DIR = Path(__file__).resolve().parent


@lru_cache(maxsize=1)
def _load_ranker():
    path = Path(os.getenv("SHOPPING_XGBOOST_MODEL_PATH", str(APP_DIR / "artifacts" / "xgboost_ranker.json")))
    if not path.exists():
        return None
    try:
        from xgboost import XGBRanker
        model = XGBRanker()
        model.load_model(str(path))
        return model
    except (ImportError, OSError, ValueError):
        return None


def _features(products, parsed):
    prices = [float(p.unit_price) for p in products]
    ratings = [float(p.rating) for p in products]
    lo_price, hi_price = min(prices), max(prices)
    lo_rating, hi_rating = min(ratings), max(ratings)
    p_span, r_span = max(hi_price - lo_price, 1e-9), max(hi_rating - lo_rating, 1e-9)
    search_terms = [str(parsed.get(k)).lower() for k in ("model_keyword", "brand", "product_type") if parsed.get(k)]
    rows = []
    for product, price, rating in zip(products, prices, ratings):
        collection = getattr(product, "collection", None)
        text = f"{product.title} {product.description} {getattr(collection, 'title', '')}".lower()
        relevance = sum(term in text for term in search_terms) / max(len(search_terms), 1)
        brand = str(parsed.get("brand") or "").lower()
        rows.append([
            price, rating, (price - lo_price) / p_span, (hi_rating - rating) / r_span,
            relevance, float(product.inventory > 0), float(bool(brand) and brand in text),
            float(parsed.get("max_price") is None or price <= float(parsed["max_price"])),
        ])
    return rows


def rank_products(products, parsed, limit=5):
    products = list(products)
    if not products:
        return [], "no_results"

    sort_by = parsed.get("sort_by")
    if sort_by == "price_ascending":
        return sorted(products, key=lambda p: (p.unit_price, -p.rating))[:limit], "explicit_price_sort"
    if sort_by == "price_descending":
        return sorted(products, key=lambda p: (-p.unit_price, -p.rating))[:limit], "explicit_price_sort"
    if sort_by == "rating_descending":
        return sorted(products, key=lambda p: (-p.rating, p.unit_price))[:limit], "explicit_rating_sort"

    model = _load_ranker()
    if model is not None:
        try:
            scores = model.predict(_features(products, parsed))
            ranked = [p for _, p in sorted(zip(scores, products), key=lambda pair: float(pair[0]), reverse=True)]
            return ranked[:limit], "xgboost"
        except (ValueError, TypeError, RuntimeError):
            pass

    prices, ratings = [float(p.unit_price) for p in products], [float(p.rating) for p in products]
    lo, hi = min(prices), max(prices)
    span = max(hi - lo, 1e-9)
    score = lambda p: 0.7 * (float(p.rating) / 5.0) + 0.3 * (1 - (float(p.unit_price) - lo) / span)
    return sorted(products, key=score, reverse=True)[:limit], "baseline_value_score"
