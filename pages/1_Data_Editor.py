import streamlit as st
import os
import sys

# Ensure the parent directory is in the path so we can import data_manager
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from data_manager import CSVDataManager

# Map the exact files found in the data/ directory
CSV_FILES = {
    "AAII History": "data/aaii_history.csv",
    "ICI History": "data/ici_history.csv",
    "Put/Call History": "data/putcall_history.csv",
}

st.set_page_config(page_title="Data Editor", layout="wide")

st.title("Contrarian Signal - Data Editor")
st.markdown(
    "Select a dataset tab below to view, edit, add, or delete records. Changes are saved directly to the underlying CSV files."
)

# Initialize the data manager
dm = CSVDataManager(CSV_FILES)

# Create distinct tabs for the 3 CSV files
tabs = st.tabs(list(CSV_FILES.keys()))

for dataset_name, tab in zip(CSV_FILES.keys(), tabs):
    with tab:
        st.subheader(f"Editing: {dataset_name}")

        # Fetch current data from the CSV
        df = dm.fetch_data(dataset_name)

        if df.empty:
            st.warning(
                f"No data found for {dataset_name}. Please verify the file path exists."
            )
            continue

        # Render the interactive editor
        edited_df = st.data_editor(
            df,
            num_rows="dynamic",  # Enables add/delete UI
            use_container_width=True,
            key=f"editor_{dataset_name}",  # Unique key per tab
            hide_index=True,
        )

        # Save button specific to the active tab
        if st.button(
            f"Save {dataset_name} Changes", key=f"save_{dataset_name}", type="primary"
        ):
            try:
                status = dm.save_data(dataset_name, edited_df)
                if status.is_ok:
                    st.success(f"{dataset_name} saved. {status.message}")
                else:
                    st.warning(
                        f"{dataset_name} saved locally but needs attention: {status.message}"
                    )
            except Exception as e:
                st.error(f"Error saving {dataset_name}: {e}")
