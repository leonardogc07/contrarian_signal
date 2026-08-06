import pandas as pd
import os


class CSVDataManager:
    def __init__(self, file_paths: dict):
        """
        Initializes the manager with a dictionary mapping
        display names to actual CSV file paths.
        """
        self.file_paths = file_paths

    def _sort_chronologically(self, df: pd.DataFrame) -> pd.DataFrame:
        """Return a copy of the frame sorted by the first date-like column."""
        if df.empty:
            return df.copy()

        date_columns = [col for col in df.columns if "date" in str(col).lower()]
        if not date_columns:
            return df.copy()

        date_column = next(
            (col for col in date_columns if str(col).lower() == "date"), None
        )
        if date_column is None:
            date_column = date_columns[0]

        try:
            parsed_dates = pd.to_datetime(df[date_column], errors="coerce")
        except (TypeError, ValueError):
            return df.copy()

        if parsed_dates.isna().all():
            return df.copy()

        sorted_df = df.copy()
        sorted_df["_sort_key"] = parsed_dates
        sorted_df = sorted_df.sort_values(
            by=["_sort_key", date_column],
            na_position="last",
            kind="mergesort",
        )
        return sorted_df.drop(columns=["_sort_key"])

    def fetch_data(self, dataset_name: str) -> pd.DataFrame:
        """Reads the CSV file and returns a Pandas DataFrame sorted chronologically."""
        path = self.file_paths.get(dataset_name)
        if path and os.path.exists(path):
            return self._sort_chronologically(pd.read_csv(path))
        return pd.DataFrame()

    def save_data(self, dataset_name: str, df: pd.DataFrame):
        """Overwrites the CSV with the newly edited DataFrame."""
        path = self.file_paths.get(dataset_name)
        if path:
            # Save without the pandas index column to keep data clean
            self._sort_chronologically(df).to_csv(path, index=False)
