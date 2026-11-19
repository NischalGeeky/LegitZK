import unittest

import field_detector


class ClinicalDetectorTests(unittest.TestCase):
    def test_labeled_identifiers_are_found_across_pages_without_leaking_values(self):
        def row(text, y):
            return [(word, (i * 36, y, i * 36 + 34, y + 8))
                    for i, word in enumerate(text.split())]

        lines = [
            [row("Avery Morgan 18/06/1968", 10),
             row("Name: Avery Morgan", 40), row("DOB: 18/06/1968", 55),
             row("Hospital ID:", 70), row("HOSP248356524", 85),
             row("Recorded Date: 15/11/2024", 100)],
            [row("Avery Morgan, born on 18/06/1968, attended follow-up.", 10),
             row("Patient record HOSP248356524", 40)],
        ]
        result = field_detector.find(lines, [(600, 200, b"")] * 2, [], use_model=False)
        labeled = [item for item in result["suggestions"] if item["method"] == "labeled_identifier"]
        for category, count in (("person_name", 3), ("birth_date", 3), ("medical_id", 2)):
            self.assertEqual(sum(item["category"] == category for item in labeled), count)
        self.assertFalse(any(item["region"][2] == 99 for item in labeled))
        self.assertNotIn("Avery Morgan", str(result))
        self.assertNotIn("18/06/1968", str(result))

    def test_financial_profile_propagates_ids_but_not_short_security_codes(self):
        texts = ["Account number: 123456789", "Reference account 123456789",
                 "IBAN: GB82 WEST 1234 5698 7654 32", "CVV: 321", "Volume: 321",
                 "Card number: 4111 1111 1111 1111"]
        rows = [[(word, (i * 42, y * 12, i * 42 + 40, y * 12 + 9))
                 for i, word in enumerate(text.split())] for y, text in enumerate(texts)]
        off = field_detector.find([rows], [(600, 100, b"")], [], use_model=False)
        on = field_detector.find([rows], [(600, 100, b"")], [], use_model=False, financial=True)
        self.assertFalse(any(item["method"] == "labeled_identifier" for item in off["suggestions"]))
        labeled = [item for item in on["suggestions"] if item["method"] == "labeled_identifier"]
        self.assertCountEqual([item["category"] for item in labeled],
                              ["account", "account", "iban", "card_security_code", "card_number"])
