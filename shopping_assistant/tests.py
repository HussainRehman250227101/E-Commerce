from django.test import SimpleTestCase
from .nlp.parser import extract_slots


class ShoppingAssistantSlotTests(SimpleTestCase):
    def test_extracts_brand_model_budget_and_rating(self):
        slots = extract_slots("Find the cheapest iPhone under Rs 5000 rated above 4.5 stars")
        self.assertEqual(slots["brand"], "Apple")
        self.assertIn("iphone", slots["model_keyword"])
        self.assertEqual(slots["max_price"], 5000.0)
        self.assertEqual(slots["min_rating"], 4.5)
        self.assertEqual(slots["sort_by"], "price_ascending")

    def test_extracts_price_range(self):
        slots = extract_slots("Show phones priced between 200 and 500")
        self.assertEqual(slots["min_price"], 200.0)
        self.assertEqual(slots["max_price"], 500.0)

    def test_limits_result_count(self):
        slots = extract_slots("Show me 20 Samsung phones")
        self.assertEqual(slots["result_limit"], 10)
