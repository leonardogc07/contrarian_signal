import tempfile
import unittest
from pathlib import Path

import pandas as pd

import data_sources as ds
from data_manager import CSVDataManager


class ICIParserTests(unittest.TestCase):
    def test_append_cache_overwrites_existing_date(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "cache.csv"
            ds._append_cache(
                path,
                {
                    "date": "2026-07-13",
                    "equity_flow_millions": 100.0,
                    "bond_flow_millions": 200.0,
                    "report_title": "old",
                },
            )
            ds._append_cache(
                path,
                {
                    "date": "2026-07-13",
                    "equity_flow_millions": 300.0,
                    "bond_flow_millions": 400.0,
                    "report_title": "new",
                },
            )

            cached = ds.load_cache(path)
            self.assertEqual(len(cached), 1)
            self.assertEqual(cached.iloc[0]["equity_flow_millions"], 300.0)
            self.assertEqual(cached.iloc[0]["bond_flow_millions"], 400.0)
            self.assertEqual(cached.iloc[0]["report_title"], "new")

    def test_extracts_inline_equity_and_bond_values_from_current_ici_html(self):
        html = """
        <html><body>
        <p><strong>Washington, DC; July 8, 2026</strong>—Total estimated outflows from long-term mutual funds were $28.87 billion for the week ended Wednesday, July 1.</p>
        <p><strong>Equity funds</strong> had estimated outflows of $29.91 billion for the week (0.2 percent of May 31 assets), compared to outflows of $16.33 billion last week.</p>
        <p><strong>Domestic equity funds</strong> had estimated outflows of $22.10 billion.</p>
        <p><strong>Bond funds</strong> had estimated inflows of $3.73 billion for the week (0.1 percent), compared to inflows of $4.75 billion during the previous week.</p>
        <p><strong>Municipal bond funds</strong> had estimated inflows of $726 million.</p>
        </body></html>
        """

        equity_flow, bond_flow = ds.parse_ici_flows_from_html(html)

        self.assertEqual(equity_flow, -29910.0)
        self.assertEqual(bond_flow, 3730.0)

    def test_fetch_data_sorts_rows_by_date_when_present(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "history.csv"
            pd.DataFrame(
                {
                    "date": ["2024-01-02", "2024-01-01", "2024-01-03"],
                    "value": [2, 1, 3],
                }
            ).to_csv(path, index=False)

            manager = CSVDataManager({"Test": str(path)})
            result = manager.fetch_data("Test")

            self.assertEqual(
                result["date"].tolist(), ["2024-01-01", "2024-01-02", "2024-01-03"]
            )

    def test_load_cache_sorts_rows_by_date_when_present(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "cache.csv"
            pd.DataFrame(
                {
                    "date": ["2024-01-02", "2024-01-01", "2024-01-03"],
                    "value": [2, 1, 3],
                }
            ).to_csv(path, index=False)

            result = ds.load_cache(path)

            self.assertEqual(
                [d.strftime("%Y-%m-%d") for d in result["date"].tolist()],
                ["2024-01-01", "2024-01-02", "2024-01-03"],
            )


if __name__ == "__main__":
    unittest.main()
