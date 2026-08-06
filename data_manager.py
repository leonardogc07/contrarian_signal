import pandas as pd
import os


class CSVDataManager:
    def __init__(self, file_paths: dict):
        """
        Initializes the manager with a dictionary mapping
        display names to actual CSV file paths.
        """
        self.file_paths = file_paths

    def fetch_data(self, dataset_name: str) -> pd.DataFrame:
        """Reads the CSV file and returns a Pandas DataFrame."""
        path = self.file_paths.get(dataset_name)
        if path and os.path.exists(path):
            return pd.read_csv(path)
        return pd.DataFrame()

    def save_data(self, dataset_name: str, df: pd.DataFrame):
        """Overwrites the CSV with the newly edited DataFrame."""
        path = self.file_paths.get(dataset_name)
        if path:
            # Save without the pandas index column to keep data clean
            df.to_csv(path, index=False)
