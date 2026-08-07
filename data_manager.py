import os
import base64
from pathlib import Path
from typing import Optional


class SyncStatus:
    def __init__(self, message: str, is_ok: bool = True):
        self.message = message
        self.is_ok = is_ok


import pandas as pd
import requests


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

    def _resolve_path(self, dataset_name: str) -> Optional[str]:
        return self.file_paths.get(dataset_name)

    def _read_local_csv(self, path: str) -> pd.DataFrame:
        if os.path.exists(path):
            return pd.read_csv(path)
        return pd.DataFrame()

    def _read_github_csv(self, path: str) -> pd.DataFrame:
        repo = os.environ.get("GITHUB_REPO")
        token = os.environ.get("GITHUB_TOKEN")
        if not repo or not token:
            return pd.DataFrame()

        try:
            url = f"https://api.github.com/repos/{repo}/contents/{path}"
            response = requests.get(
                url, headers={"Authorization": f"token {token}"}, timeout=15
            )
            response.raise_for_status()
            payload = response.json()
            content = payload.get("content", "")
            if not content:
                return pd.DataFrame()
            decoded = base64.b64decode(content).decode("utf-8")
            return pd.read_csv(pd.io.common.StringIO(decoded))
        except (requests.RequestException, ValueError, KeyError, TypeError):
            return pd.DataFrame()

    def fetch_data(self, dataset_name: str) -> pd.DataFrame:
        """Reads the CSV file and returns a Pandas DataFrame sorted chronologically."""
        path = self._resolve_path(dataset_name)
        if not path:
            return pd.DataFrame()

        local_df = self._read_local_csv(path)
        if not local_df.empty:
            return self._sort_chronologically(local_df)

        github_df = self._read_github_csv(path)
        if not github_df.empty:
            return self._sort_chronologically(github_df)

        return pd.DataFrame()

    def save_data(self, dataset_name: str, df: pd.DataFrame) -> SyncStatus:
        """Overwrite the CSV locally and mirror the update to GitHub when configured."""
        path = self._resolve_path(dataset_name)
        if not path:
            return SyncStatus(
                "No target path configured for this dataset.", is_ok=False
            )

        sorted_df = self._sort_chronologically(df)
        sorted_df.to_csv(path, index=False)

        repo = os.environ.get("GITHUB_REPO")
        token = os.environ.get("GITHUB_TOKEN")
        if not repo or not token:
            return SyncStatus(
                "Saved locally. GitHub sync is not configured.", is_ok=True
            )

        try:
            file_path = Path(path)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            content = sorted_df.to_csv(index=False).encode("utf-8")
            encoded = base64.b64encode(content).decode("utf-8")
            url = f"https://api.github.com/repos/{repo}/contents/{path}"
            response = requests.put(
                url,
                headers={
                    "Authorization": f"token {token}",
                    "Accept": "application/vnd.github+json",
                },
                json={
                    "message": f"Update {file_path.name}",
                    "content": encoded,
                },
                timeout=20,
            )
            response.raise_for_status()
            return SyncStatus("Saved locally and synced to GitHub.", is_ok=True)
        except requests.RequestException:
            return SyncStatus("Saved locally, but GitHub sync failed.", is_ok=False)
