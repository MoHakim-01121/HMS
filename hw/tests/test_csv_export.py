"""CSV exports: text that a spreadsheet would run as a formula is neutralised;
numbers, phone numbers and the '-' placeholder stay as they are."""
import csv
import io

from django.test import SimpleTestCase

from hw.views.helpers import csv_export_response


def exported_row(*values):
    resp = csv_export_response('x.csv', ['a'] * len(values), [list(values)], bom=False)
    return list(csv.reader(io.StringIO(resp.content.decode())))[1]


class CsvFormulaTests(SimpleTestCase):
    def test_formula_text_is_neutralised(self):
        for value in ('=1+1', '@SUM(A1)', '+cmd|calc', '-2+3+cmd', '\tx=1', '\r=1'):
            with self.subTest(value=value):
                self.assertEqual(exported_row(value), [f"'{value}"])

    def test_values_that_only_look_risky_are_kept(self):
        for value in ('-', '-1,500.25', '+62 812-3456-7890', 'PT Sahabat', ''):
            with self.subTest(value=value):
                self.assertEqual(exported_row(value), [value])

    def test_non_text_values_are_untouched(self):
        self.assertEqual(exported_row(-5, 1.5, None), ['-5', '1.5', ''])
