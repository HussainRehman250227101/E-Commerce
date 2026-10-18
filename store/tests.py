from django.test import TestCase

from django.test import SimpleTestCase

from store.recommender import ContentIndex, ProductDocument


def _doc(product_id, title, description, collection_id, collection_title, price, rating):
    return ProductDocument(
        id=product_id,
        title=title,
        description=description,
        collection_id=collection_id,
        collection_title=collection_title,
        unit_price=price,
        rating=rating,
    )


SHIRTS = 1
SHOES = 2


class ContentBasedFilteringTests(SimpleTestCase):
    def setUp(self):
        self.documents = [
            _doc(1, "Blue cotton shirt", "soft cotton button shirt for summer", SHIRTS, "Shirts", 20, 4.5),
            _doc(2, "Navy cotton shirt", "casual cotton shirt with buttons", SHIRTS, "Shirts", 22, 4.4),
            _doc(3, "Road running shoes", "lightweight road running sneakers", SHOES, "Shoes", 80, 4.8),
            _doc(4, "Trail running shoes", "grippy trail running sneakers", SHOES, "Shoes", 90, 4.6),
        ]
        self.index = ContentIndex.build(self.documents)

    def test_shirt_matches_another_shirt_ahead_of_shoes(self):
        ranked = self.index.similar_to(1, limit=3)
        self.assertEqual(ranked[0].product_id, 2)
        self.assertNotIn(3, [item.product_id for item in ranked])
        self.assertIn("cotton", ranked[0].matched_terms)
        self.assertTrue(any("Shirts" in reason for reason in ranked[0].reasons))

    def test_shopper_who_bought_a_shirt_is_offered_another_shirt(self):
        ranked = self.index.recommend_from_seeds([1], limit=3, exclude_ids={1})
        self.assertEqual(ranked[0].product_id, 2)
        self.assertNotIn(1, [item.product_id for item in ranked])
        self.assertEqual(ranked[0].anchor_title, "Blue cotton shirt")

    def test_identical_content_scores_higher_than_a_different_category(self):
        twin = _doc(5, "Blue cotton shirt", "soft cotton button shirt for summer", SHIRTS, "Shirts", 20, 4.5)
        index = ContentIndex.build(self.documents + [twin])
        ranked = index.similar_to(1, limit=4)
        self.assertEqual(ranked[0].product_id, 5)
        self.assertGreater(ranked[0].similarity, 0.9)

    def test_unknown_product_returns_no_neighbors(self):
        self.assertEqual(self.index.similar_to(999), [])

    def test_visit_to_a_shirt_recommends_another_shirt(self):
        ranked = self.index.recommend_from_activity(visit_ids=[1], limit=3)
        self.assertEqual(ranked[0].product_id, 2)
        self.assertTrue(any("viewed" in reason for reason in ranked[0].reasons))

    def test_search_for_running_shoes_ranks_a_shoe(self):
        ranked = self.index.recommend_from_activity(search_text="running shoes", limit=3)
        self.assertIn(ranked[0].product_id, {3, 4})
        self.assertTrue(any("search" in reason for reason in ranked[0].reasons))

    def test_empty_history_returns_no_profile_matches(self):
        self.assertEqual(self.index.recommend_from_seeds([], limit=4), [])
