"""Schema validation: what the pipeline refuses, and why."""

from __future__ import annotations

import unittest

from mb.model import Day, Item, Relevance, SectionError
from mb.paths import DateError, day_path, item_filename, parse_item_filename


class ItemValidationTests(unittest.TestCase):
    def _item(self, **overrides):
        record = {"id": "aapl", "section": "stocks", "label": "AAPL", "text": "flat"}
        record.update(overrides)
        return record

    def test_minimal_item_is_valid(self):
        item = Item.from_json(self._item())
        self.assertEqual(item.id, "aapl")
        self.assertEqual(item.kind, "item")
        self.assertEqual(item.order, 100)

    def test_structured_fields_alone_are_enough(self):
        """A holdings line can come from numbers only — no prose required."""
        item = Item.from_json({"id": "aapl", "section": "stocks", "ticker": "AAPL", "price": 342.56})
        self.assertEqual(item.data["ticker"], "AAPL")

    def test_empty_item_is_rejected(self):
        with self.assertRaises(SectionError):
            Item.from_json({"id": "aapl", "section": "stocks"})

    def test_typo_in_field_name_is_rejected(self):
        with self.assertRaisesRegex(SectionError, "soruces"):
            Item.from_json(self._item(soruces=["https://x"]))

    def test_foreign_section_field_is_rejected(self):
        """`ticker` is a stocks field; letting it into weather hides typos."""
        with self.assertRaisesRegex(SectionError, "unknown field"):
            Item.from_json({"id": "x", "section": "weather", "text": "a", "ticker": "AAPL"})

    def test_bad_section_is_rejected(self):
        with self.assertRaisesRegex(SectionError, "section"):
            Item.from_json(self._item(section="sport"))

    def test_bad_id_is_rejected(self):
        with self.assertRaisesRegex(SectionError, "id"):
            Item.from_json(self._item(id="AAPL price"))

    def test_sources_accept_strings_and_objects(self):
        item = Item.from_json(
            self._item(sources=["https://a", {"title": "B", "url": "https://b"}])
        )
        self.assertEqual(item.sources[0]["url"], "https://a")
        self.assertEqual(item.sources[1]["title"], "B")

    def test_source_without_url_is_rejected(self):
        with self.assertRaisesRegex(SectionError, "url"):
            Item.from_json(self._item(sources=[{"title": "B"}]))

    def test_round_trip_is_stable(self):
        item = Item.from_json(self._item(sources=["https://a"], order=20))
        again = Item.from_json(item.to_json())
        self.assertEqual(again.to_json(), item.to_json())

    def test_filename_is_order_padded(self):
        self.assertEqual(Item.from_json(self._item(order=3)).filename(), "03-aapl.json")
        self.assertEqual(parse_item_filename("03-aapl.json"), (3, "aapl"))
        self.assertIsNone(parse_item_filename("meta.json"))
        self.assertEqual(item_filename(12, "x"), "12-x.json")


class RelevanceTests(unittest.TestCase):
    def test_decide_rule_table(self):
        self.assertEqual(Relevance.decide(True, True), "keep")
        self.assertEqual(Relevance.decide(True, False), "keep")
        self.assertEqual(Relevance.decide(False, True), "context")
        self.assertEqual(Relevance.decide(False, False), "drop")

    def test_bad_category_is_rejected(self):
        with self.assertRaisesRegex(SectionError, "category"):
            Relevance.from_json({"brief": True, "price_move": False, "category": "vibes"}, where="x")

    def test_bad_verdict_is_rejected(self):
        with self.assertRaisesRegex(SectionError, "verdict"):
            Relevance.from_json({"brief": True, "price_move": False, "verdict": "maybe"}, where="x")

    def test_news_entry_needs_headline_or_summary(self):
        with self.assertRaisesRegex(SectionError, "headline or a summary"):
            Item.from_json({"id": "a", "section": "stocks", "news": [{"published": "2026-11-20"}]})


class DayTests(unittest.TestCase):
    def test_flat_and_nested_dates_agree(self):
        self.assertEqual(Day.from_json({"date": "2026-11-22"}).date.nested, "2026/11/22")
        self.assertEqual(Day.from_json({"date": "2026/11/22"}).date.flat, "2026-11-22")

    def test_unknown_meta_field_is_rejected(self):
        with self.assertRaisesRegex(SectionError, "unknown field"):
            Day.from_json({"date": "2026-11-22", "locaton": "Sofia"})

    def test_bad_date_is_rejected(self):
        with self.assertRaisesRegex(DateError, "month/day out of range"):
            day_path("2026-13-45")
        with self.assertRaisesRegex(DateError, "expected YYYY-MM-DD"):
            day_path("yesterday")


if __name__ == "__main__":
    unittest.main()
