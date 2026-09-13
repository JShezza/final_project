# NextTrack

A stateless RESTful API for music recommendation. Given a short list of seed
tracks and preference parameters
it returns a suitable next track (without storing user profiles)

Recommendations come form a **hybrid** of three signals which are then combined
by a weighted blender the user can steer:

- Audio:
  - FAISS nearest-neighbour over Spotify audio features. This summarises what
    a track sounds like.
- Collaborative:
  - Using Last.fm `track.getSimilar` it gathers what songs are frequently
    played with the track.
- Lyric:
  - LRCLIB lyrics scored with VADER to gather the "mood" of the song from
    words

Prefeerence parameters adjust the blend per request: **novelty** biases away from
popular tracks, towards the long tail and **target_mood** steers the search using
valence and energy.

Noinformation about the call is stored. All requests are anonymous. The optional
`user_id` is an opaque key, hashed before it's logged and only used for A/B variant
assignments.

## Requirements

All dependencies are stored in requirements.txt however:

- Python 3.11+
- Node 18+
- `tracks_features.csv` dataset ([~1.2M Spotify tracks with audio features](https://www.kaggle.com/datasets/rodolfofigueroa/spotify-12m-songs))
- optional: [last.fm API Key](https://www.last.fm/api/account/create). If not used
  the API will use audio-only.

## Set up

1. python dependencies

```bash
pip install -r requirements.txt
```

1. enviroment variables - rename .env.example to .env and input values.

```bash
cp .env.example .env
```

1. build the search index (can take a few minutes as it reads tracks_features.csv
   and writes the data)

```bash
python prepare_data.py
```

`prepare_data.py` expects `tracks_feature.csv` in the same directory. You can change
`CSV_PATH` at the top of the file if you want it moved elsewhere. **The program
does not work until this is done** - The recommender, API and the benchmark all
write their data to `data/`.

## Running the program

```bash
# from inside src/
uvicorn main:app
```

Documentation is automatically generated from Pydantic models at <http://127.0.0.1:8000/docs>

For inside the src/web/ directory:

```bash
npm install
npm run dev
```

Server is accessible at <http://localhost:5173>. Tracks can be searched, added,
and request recommendations. Each result shows how much a signal contributes to
the recommendation. You are also able to use a Spotify player to preview the
songs for 30 seocnds.

## Tests

```bash
pytest                          # Runs everything
pytest tests/test_routes.py     # Run a specific test file
```

- `test_blender` - Weighted fusion, Normalisation, novelty, rationale arithmetic
- `test_integration.py` - /recommend pipeline end to end over HTTP
- `test_routes.py` - Supporting routes, mood analysis and JWT admin
- `test_lastfm_adapter.py` - Collaborative adapter parsing and caching
- `test_lyric_signal.py` - Lyric fetching, sentiment analysis scoring and cache
  behaviour.

The test suite doesn't need any network access or API keys as external services
are replaced with recorded fixtures.

## Evaluation

Index accuracy and latency: approximate vs exact search

```bash
python eval.py
```

Variant benchmark: 40 seed tracks across 4 genres

```bash
python -m benchmarks.benchmark      # -m is used as the benchmark lives in a package and imports from the project root.
```

The benchmark compares all A/B variants against a random control on coheerence,
diversity, popularity coverage and lyrics, with Wilcoxon signed-ranked tests paired
per seed. It also sweeps the novelty parameter and the mood settings. Results are
saveed to `benchmarks/benchmark_results.json` and `benchmarks/benchmark_mood.json`.

As the lyrics need to be fetched from LRCLIB it can take awhile first run. Everything
is cached in `data/lyrics_cache` once ran. `LASTFM_API_KEY` must be set before running,
or the collaborative column will be left empty
