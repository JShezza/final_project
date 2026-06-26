import pickle
import time
from pathlib import Path

import faiss
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

DATA_DIR = Path(__file__).parent / "data"
CSV_PATH = "tracks_features.csv"
NLIST = 1024  # Voroni cells

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
    X = df[FEATURES].to_numpy(dtype="float32")

    # Standardise - mean 0 std 1 per feature. without, tempo 0-249
    scaler = StandardScaler()
    X = scaler.fit_transform(X).astype("float32")

    # Dimension - features per vector
    dim = X.shape[1]
    # IVF index - Don't compare against every vector. Chop space into NLIST and check closet on search
    quantiser = faiss.IndexFlatL2(dim)
    index = faiss.IndexIVFFlat(quantiser, dim, NLIST, faiss.METRIC_L2)

    print(f"Training index on {len(X):,} vectors ({dim} dims)...")
    t0 = time.time()
    index.train(X)  # Learn chunk boundaries
    index.add(X)  # Load the vectors in
    print(f"Index built in {time.time() - t0:.1f}s, ntotal={index.ntotal:,}")

    return index, scaler


def main():
    DATA_DIR.mkdir(exist_ok=True)
    print("Loading data...")
    df = load_data(CSV_PATH)

    index, scaler = build_faiss(df)

    faiss.write_index(index, str(DATA_DIR / "tracks.index"))
    with open(DATA_DIR / "scaler.pkl", "wb") as f:
        pickle.dump(scaler, f)

    # Keep the original row order with matching FAISS ids
    meta = df[["id", "name", "artists", "year"]].reset_index(drop=True)
    meta.to_pickle(DATA_DIR / "metadata.pkl")

    # Match id -> position allows look up by spotify id
    id_to_pos = {tid: i for i, tid in enumerate(meta["id"].tolist())}
    with open(DATA_DIR / "id_to_pos.pkl", "wb") as f:
        pickle.dump(id_to_pos, f)

    print("Saved artifacts to: ", DATA_DIR)


if __name__ == "__main__":
    main()
