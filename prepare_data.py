from pathlib import Path

import faiss
import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).parent / "data"
CSV_PATH = "tracks_features.csv"

# Audio features from data set. Ignoring categorical and time
FEATURES = [
    "danceability",
    "energy",
    "loudness",
    "speechiness",
    "acousticness",
    "instrumentalness",
    "liveness",
    "valence",
    "tempo",
]


def load_data(csv_path: str) -> pd.DataFrame:
    """Read columns needed."""
    cols = ["id", "name", "artists", "year"] + FEATURES
    df = pd.read_csv(csv_path, usecols=cols)

    # Format artists column
    df["artists"] = df["artists"].str.replace(r"[\[\]']", "", regex=True).str.strip()

    return df


def build_faiss(df: pd.DataFrame):
    """Train FAISS IVF index and Scale features."""
    return


def main():
    DATA_DIR.mkdir(exist_ok=True)
    print("Loading data...")
    df = load_data(CSV_PATH)

    return


if __name__ == "__main__":
    main()
