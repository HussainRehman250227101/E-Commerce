"""Content-based filtering for the store catalog.

Each product becomes a profile made from its own content:

- words in the title and description (TF-IDF)
- collection
- price
- rating

A shopper profile is a weighted average of products they opened, added to
the cart, or ordered, plus the words they searched for. Cosine similarity
then ranks the catalog against that profile, or against one product when
the shopper is looking at a product page.

This does not use other shoppers' behavior. That would be collaborative
filtering. Here, two products match because they are about the same thing.
"""

from __future__ import annotations

import math
import re
import threading
from collections import Counter
from dataclasses import dataclass, field

TOKEN_RE = re.compile(r"[a-z0-9]+")

# Feature blend. Text does most of the work; the other signals break ties
# when two products talk about the same thing but sit in different aisles
# or price ranges.
TEXT_WEIGHT = 0.65
COLLECTION_WEIGHT = 0.20
PRICE_WEIGHT = 0.10
RATING_WEIGHT = 0.05

# Stronger actions pull the shopper profile harder than a quick page visit.
VISIT_WEIGHT = 1.0
CART_WEIGHT = 2.5
ORDER_WEIGHT = 3.0
SEARCH_WEIGHT = 2.0

# Drop matches that are only a rounding artifact.
MIN_SIMILARITY = 0.05

STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "if", "then", "else", "when",
    "at", "by", "for", "with", "about", "against", "between", "into",
    "through", "during", "before", "after", "above", "below", "to", "from",
    "up", "down", "in", "out", "on", "off", "over", "under", "again",
    "further", "once", "here", "there", "all", "any", "both", "each",
    "few", "more", "most", "other", "some", "such", "no", "nor", "not",
    "only", "own", "same", "so", "than", "too", "very", "can", "will",
    "just", "should", "now", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "of", "this",
    "that", "these", "those", "it", "its", "you", "your", "our", "we",
    "they", "them", "their", "as", "also", "product", "products",
}

METHOD_SUMMARY = (
    "Content-based filtering. Each product is a TF-IDF vector of its title "
    "and description, blended with collection, price, and rating. "
    "Cosine similarity ranks the closest products."
)

FEATURE_WEIGHTS = {
    "text": TEXT_WEIGHT,
    "collection": COLLECTION_WEIGHT,
    "price": PRICE_WEIGHT,
    "rating": RATING_WEIGHT,
}


@dataclass(frozen=True)
class ProductDocument:
    id: int
    title: str
    description: str
    collection_id: int
    collection_title: str
    unit_price: float
    rating: float


@dataclass(frozen=True)
class Recommendation:
    product_id: int
    similarity: float
    reasons: list[str]
    matched_terms: list[str]
    anchor_product_id: int | None = None
    anchor_title: str | None = None
    parts: dict[str, float] = field(default_factory=dict)


def tokenize(text: str) -> list[str]:
    tokens = TOKEN_RE.findall((text or "").lower())
    return [token for token in tokens if len(token) > 1 and token not in STOPWORDS]


def _l2_normalize(weights: dict[str, float]) -> dict[str, float]:
    norm = math.sqrt(sum(weight * weight for weight in weights.values()))
    if norm == 0:
        return {}
    return {term: weight / norm for term, weight in weights.items()}


def _cosine(left: dict[str, float], right: dict[str, float]) -> float:
    """Both vectors are L2-normalized, so cosine similarity is their dot product."""
    if len(left) > len(right):
        left, right = right, left
    return sum(weight * right.get(term, 0.0) for term, weight in left.items())


def _closeness(left: float, right: float, scale: float) -> float:
    if scale <= 0:
        return 1.0
    return max(0.0, 1.0 - abs(left - right) / scale)


class ContentIndex:
    """In-memory catalog index. Rebuild when products change."""

    def __init__(
        self,
        documents: list[ProductDocument],
        vectors: dict[int, dict[str, float]],
        idf: dict[str, float] | None = None,
    ):
        self.documents = documents
        self.by_id = {document.id: document for document in documents}
        self.vectors = vectors
        self.idf = idf or {}
        prices = [document.unit_price for document in documents]
        self.price_scale = (max(prices) - min(prices)) if prices else 0.0

    @classmethod
    def build(cls, documents: list[ProductDocument]) -> "ContentIndex":
        tokenized: dict[int, list[str]] = {}
        document_frequency: Counter[str] = Counter()

        for document in documents:
            # Title is written twice so the product name outweighs a long description.
            tokens = tokenize(f"{document.title} {document.title} {document.description}")
            tokenized[document.id] = tokens
            document_frequency.update(set(tokens))

        catalog_size = len(documents)
        idf = {
            term: math.log((1 + catalog_size) / (1 + frequency)) + 1
            for term, frequency in document_frequency.items()
        }
        vectors: dict[int, dict[str, float]] = {}
        for document in documents:
            tokens = tokenized[document.id]
            if not tokens:
                vectors[document.id] = {}
                continue

            counts = Counter(tokens)
            length = float(len(tokens))
            raw = {
                term: (count / length) * idf[term]
                for term, count in counts.items()
            }
            vectors[document.id] = _l2_normalize(raw)

        return cls(documents, vectors, idf)

    def similar_to(self, product_id: int, limit: int = 8) -> list[Recommendation]:
        source = self.by_id.get(product_id)
        if source is None:
            return []

        ranked = [
            self._score_pair(source, candidate, anchor=source)
            for candidate in self.documents
            if candidate.id != product_id
        ]
        return self._top(ranked, limit)

    def recommend_from_seeds(
        self,
        seed_ids: list[int],
        limit: int = 8,
        exclude_ids: set[int] | None = None,
    ) -> list[Recommendation]:
        """Build a shopper profile from products they already chose."""
        blocked = set(exclude_ids or ())
        seeds = []
        seen = set()
        for seed_id in seed_ids:
            if seed_id in seen or seed_id not in self.by_id:
                continue
            seen.add(seed_id)
            seeds.append(self.by_id[seed_id])
            blocked.add(seed_id)

        if not seeds:
            return []

        profile_vector = self._mean_vector(seeds)
        mean_price = sum(seed.unit_price for seed in seeds) / len(seeds)
        mean_rating = sum(seed.rating for seed in seeds) / len(seeds)
        collection_weights: dict[int, float] = {}
        for seed in seeds:
            collection_weights[seed.collection_id] = collection_weights.get(seed.collection_id, 0.0) + 1
        for collection_id in collection_weights:
            collection_weights[collection_id] /= len(seeds)

        ranked = []
        for candidate in self.documents:
            if candidate.id in blocked:
                continue
            anchor = max(seeds, key=lambda seed: _cosine(self.vectors[seed.id], self.vectors[candidate.id]))
            ranked.append(
                self._score_against_profile(
                    candidate,
                    profile_vector,
                    mean_price,
                    mean_rating,
                    collection_weights,
                    anchor,
                )
            )
        return self._top(ranked, limit)

    def recommend_from_activity(
        self,
        cart_ids: list[int] | None = None,
        order_ids: list[int] | None = None,
        visit_ids: list[int] | None = None,
        search_text: str = "",
        limit: int = 8,
    ) -> list[Recommendation]:
        """Rank the catalog from visits, search text, cart items, and orders."""
        chosen: dict[int, tuple[float, str]] = {}
        for source, ids, weight in (
            ("visit", visit_ids or [], VISIT_WEIGHT),
            ("cart", cart_ids or [], CART_WEIGHT),
            ("order", order_ids or [], ORDER_WEIGHT),
        ):
            for product_id in ids:
                if product_id not in self.by_id:
                    continue
                current = chosen.get(product_id)
                if current is None or weight > current[0]:
                    chosen[product_id] = (weight, source)

        seeds = [
            (self.by_id[product_id], weight, source)
            for product_id, (weight, source) in chosen.items()
        ]
        search_vector = self.vector_from_text(search_text)
        if not seeds and not search_vector:
            return []

        vector_parts: list[tuple[dict[str, float], float]] = [
            (self.vectors[document.id], weight) for document, weight, _source in seeds
        ]
        if search_vector:
            vector_parts.append((search_vector, SEARCH_WEIGHT))
        profile_vector = self._weighted_mean(vector_parts)

        weight_total = sum(weight for _document, weight, _source in seeds) or 1.0
        if seeds:
            mean_price = sum(document.unit_price * weight for document, weight, _source in seeds) / weight_total
            mean_rating = sum(document.rating * weight for document, weight, _source in seeds) / weight_total
            collection_weights: dict[int, float] = {}
            for document, weight, _source in seeds:
                collection_weights[document.collection_id] = (
                    collection_weights.get(document.collection_id, 0.0) + weight
                )
            for collection_id in collection_weights:
                collection_weights[collection_id] /= weight_total
        else:
            mean_price = 0.0
            mean_rating = 0.0
            collection_weights = {}

        blocked = set(chosen)
        ranked = []
        for candidate in self.documents:
            if candidate.id in blocked:
                continue
            anchor = None
            if seeds:
                anchor_document, _anchor_weight, anchor_source = max(
                    seeds,
                    key=lambda item: _cosine(self.vectors[item[0].id], self.vectors[candidate.id]),
                )
                anchor = (anchor_document, anchor_source)
            ranked.append(
                self._score_activity(
                    candidate,
                    profile_vector,
                    mean_price,
                    mean_rating,
                    collection_weights,
                    anchor,
                    bool(seeds),
                    search_text,
                )
            )
        return self._top(ranked, limit)

    def vector_from_text(self, text: str) -> dict[str, float]:
        tokens = tokenize(text)
        if not tokens or not self.idf:
            return {}
        counts = Counter(tokens)
        length = float(len(tokens))
        raw = {
            term: (count / length) * self.idf[term]
            for term, count in counts.items()
            if term in self.idf
        }
        return _l2_normalize(raw)

    def _weighted_mean(self, parts: list[tuple[dict[str, float], float]]) -> dict[str, float]:
        totals: dict[str, float] = {}
        weight_sum = sum(weight for _vector, weight in parts) or 1.0
        for vector, weight in parts:
            for term, value in vector.items():
                totals[term] = totals.get(term, 0.0) + value * weight
        return _l2_normalize({term: value / weight_sum for term, value in totals.items()})

    def _score_activity(
        self,
        candidate: ProductDocument,
        profile_vector: dict[str, float],
        mean_price: float,
        mean_rating: float,
        collection_weights: dict[int, float],
        anchor: tuple[ProductDocument, str] | None,
        has_product_seeds: bool,
        search_text: str,
    ) -> Recommendation:
        text_score = _cosine(profile_vector, self.vectors[candidate.id])
        collection_score = collection_weights.get(candidate.collection_id, 0.0) if has_product_seeds else 0.0
        price_score = _closeness(mean_price, candidate.unit_price, self.price_scale) if has_product_seeds else 0.0
        rating_score = _closeness(mean_rating, candidate.rating, 5.0) if has_product_seeds else 0.0
        matched_terms = self._matched_terms_with_vector(profile_vector, candidate.id)
        reasons = []
        if anchor is not None:
            anchor_document, anchor_source = anchor
            if anchor_source == "visit":
                reasons.append(f"Because you viewed {anchor_document.title}")
            elif anchor_source == "cart":
                reasons.append(f"Because it is in your cart, similar to {anchor_document.title}")
            elif anchor_source == "order":
                reasons.append(f"Because you ordered {anchor_document.title}")
        if search_text.strip() and matched_terms:
            reasons.append("Matches your search: " + ", ".join(matched_terms))
        if collection_score >= 0.34:
            reasons.append(f"Matches a collection you already shop: {candidate.collection_title}")
        if not reasons:
            reasons.append("Closest overall match to your browsing")
        anchor_document = anchor[0] if anchor else candidate
        return self._recommendation(
            candidate,
            text_score,
            collection_score,
            price_score,
            rating_score,
            matched_terms,
            reasons,
            anchor_document,
        )

    def _mean_vector(self, seeds: list[ProductDocument]) -> dict[str, float]:
        totals: dict[str, float] = {}
        for seed in seeds:
            for term, weight in self.vectors[seed.id].items():
                totals[term] = totals.get(term, 0.0) + weight
        scale = float(len(seeds))
        return _l2_normalize({term: weight / scale for term, weight in totals.items()})

    def _score_pair(
        self,
        source: ProductDocument,
        candidate: ProductDocument,
        anchor: ProductDocument,
    ) -> Recommendation:
        text_score = _cosine(self.vectors[source.id], self.vectors[candidate.id])
        collection_score = 1.0 if source.collection_id == candidate.collection_id else 0.0
        price_score = _closeness(source.unit_price, candidate.unit_price, self.price_scale)
        rating_score = _closeness(source.rating, candidate.rating, 5.0)
        matched_terms = self._matched_terms(source.id, candidate.id)
        reasons = self._pair_reasons(source, candidate, matched_terms, price_score, rating_score)
        return self._recommendation(
            candidate,
            text_score,
            collection_score,
            price_score,
            rating_score,
            matched_terms,
            reasons,
            anchor,
        )

    def _score_against_profile(
        self,
        candidate: ProductDocument,
        profile_vector: dict[str, float],
        mean_price: float,
        mean_rating: float,
        collection_weights: dict[int, float],
        anchor: ProductDocument,
    ) -> Recommendation:
        text_score = _cosine(profile_vector, self.vectors[candidate.id])
        collection_score = collection_weights.get(candidate.collection_id, 0.0)
        price_score = _closeness(mean_price, candidate.unit_price, self.price_scale)
        rating_score = _closeness(mean_rating, candidate.rating, 5.0)
        matched_terms = self._matched_terms_with_vector(profile_vector, candidate.id)
        reasons = []
        if anchor.id != candidate.id:
            reasons.append(f"Similar to {anchor.title}")
        if collection_score >= 0.34:
            reasons.append(f"Matches a collection you already shop: {candidate.collection_title}")
        if matched_terms:
            reasons.append("Shares words with items you chose: " + ", ".join(matched_terms))
        if price_score >= 0.75:
            reasons.append("Close to your usual price")
        if not reasons:
            reasons.append("Closest overall match to items you chose")
        return self._recommendation(
            candidate,
            text_score,
            collection_score,
            price_score,
            rating_score,
            matched_terms,
            reasons,
            anchor,
        )

    def _recommendation(
        self,
        candidate: ProductDocument,
        text_score: float,
        collection_score: float,
        price_score: float,
        rating_score: float,
        matched_terms: list[str],
        reasons: list[str],
        anchor: ProductDocument,
    ) -> Recommendation:
        similarity = (
            TEXT_WEIGHT * text_score
            + COLLECTION_WEIGHT * collection_score
            + PRICE_WEIGHT * price_score
            + RATING_WEIGHT * rating_score
        )
        return Recommendation(
            product_id=candidate.id,
            similarity=similarity,
            reasons=reasons,
            matched_terms=matched_terms,
            anchor_product_id=anchor.id,
            anchor_title=anchor.title,
            parts={
                "text": round(text_score, 4),
                "collection": round(collection_score, 4),
                "price": round(price_score, 4),
                "rating": round(rating_score, 4),
            },
        )

    def _pair_reasons(
        self,
        source: ProductDocument,
        candidate: ProductDocument,
        matched_terms: list[str],
        price_score: float,
        rating_score: float,
    ) -> list[str]:
        reasons = []
        if source.collection_id == candidate.collection_id:
            reasons.append(f"Same collection: {candidate.collection_title}")
        if matched_terms:
            reasons.append("Shared words: " + ", ".join(matched_terms))
        if price_score >= 0.75:
            reasons.append("Similar price")
        if rating_score >= 0.8:
            reasons.append("Similar customer rating")
        if not reasons:
            reasons.append("Closest overall content match")
        return reasons

    def _matched_terms(self, left_id: int, right_id: int, top_k: int = 3) -> list[str]:
        return self._matched_terms_with_vector(self.vectors[left_id], right_id, top_k)

    def _matched_terms_with_vector(
        self,
        left: dict[str, float],
        right_id: int,
        top_k: int = 3,
    ) -> list[str]:
        right = self.vectors[right_id]
        overlap = [
            (left[term] * right[term], term)
            for term in left.keys() & right.keys()
        ]
        overlap.sort(reverse=True)
        return [term for _, term in overlap[:top_k]]

    def _top(self, ranked: list[Recommendation], limit: int) -> list[Recommendation]:
        ranked.sort(key=lambda item: item.similarity, reverse=True)
        kept = []
        for item in ranked:
            text_score = item.parts.get("text", 0.0)
            collection_score = item.parts.get("collection", 0.0)
            # Price and rating only break ties. They cannot recommend a product alone.
            if item.similarity < MIN_SIMILARITY:
                continue
            if text_score <= 0 and collection_score <= 0:
                continue
            kept.append(item)
            if len(kept) == limit:
                break
        return kept


_index_cache: dict = {"signature": None, "index": None}
_index_lock = threading.Lock()


def _signature():
    from .models import Product

    return tuple(Product.objects.order_by("id").values_list("id", "last_update"))


def _documents() -> list[ProductDocument]:
    from .models import Product

    documents = []
    products = Product.objects.select_related("collection").order_by("id")
    for product in products:
        documents.append(
            ProductDocument(
                id=product.id,
                title=product.title,
                description=product.description or "",
                collection_id=product.collection_id,
                collection_title=product.collection.title,
                unit_price=float(product.unit_price),
                rating=float(product.rating),
            )
        )
    return documents


def get_content_index(force: bool = False) -> ContentIndex:
    """Reuse the index until a product is created, edited, or deleted."""
    signature = _signature()
    with _index_lock:
        cached = _index_cache["index"]
        if not force and cached is not None and _index_cache["signature"] == signature:
            return cached
        index = ContentIndex.build(_documents())
        _index_cache["signature"] = signature
        _index_cache["index"] = index
        return index
