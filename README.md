# NextTrack

A stateless RESTful API for music recommendation. Given a short list of seed
tracks and preference parameters, it returns a suitable next track without
storing user profiles.

Recommendations come from a **hybrid** of three signals, combined by a weighted
blender the user can steer:

- **Audio** — FAISS nearest-neighbour search over Spotify audio features. This
summarises what a track sounds like.
- **Collaborative** — Last.fm `track.getSimilar` gathers the songs that are
frequently played alongside the track.
- **Lyric** — LRCLIB lyrics scored with VADER to gather the "mood" of the song
from its words.
Preference parameters adjust the blend per request: **novelty** biases away from
popular tracks and towards the long tail, and **target_mood** steers the search
using valence and energy.

No information about the caller is stored and all requests are anonymous. The
optional `user_id` is an opaque key, hashed before it is logged and used only
for A/B variant assignment.

## Requirements

All dependencies are listed in `requirements.txt`, but you will also need:

- Python 3.11+
- Node 18+
- The `tracks_features.csv` dataset ([~1.2M Spotify tracks with audio features](https://www.kaggle.com/datasets/rodolfofigueroa/spotify-12m-songs))
- Optional: a [Last.fm API key](https://www.last.fm/api/account/create). Without
one the API runs audio-only.

## Set up

1. Install the Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Set the environment variables — copy `.env.example` to `.env` and fill in the
values:
   ```bash
   cp .env.example .env
   ```

   | Variable | Purpose |
   | --- | --- |
   | `LASTFM_API_KEY` | Collaborative signal. Omit it to run audio-only. |
   | `AB_TESTING` | `true` assigns strategies automatically; `false` lets the user choose one. |
   | `ADMIN_USERNAME`, `ADMIN_PASSWORD` | Login for the admin routes. |
   | `JWT_SECRET` | Signs the admin tokens. Any long random string. |

3. Build the search index. This can take a few minutes, as it reads
   `tracks_features.csv` and writes the artifacts to `data/`:
   ```bash
   python prepare_data.py
   ```

`prepare_data.py` expects `tracks_features.csv` in the same directory. You can
change `CSV_PATH` at the top of the file if you keep it elsewhere. **Nothing
else runs until this is done** — the recommender, the API and the benchmark all
load the artifacts it writes to `data/`.

## Running the program

```bash
# from inside src/
uvicorn main:app
```

Documentation is generated automatically from the Pydantic models at
<http://127.0.0.1:8000/docs>.

From inside `src/web/`:

```bash
npm install
npm run dev
```

The client is then available at <http://localhost:5173>. Tracks can be searched
and added as seeds, and recommendations requested. Each result shows how much
every signal contributed to it, and an embedded Spotify player previews the song
for 30 seconds. With `AB_TESTING=false` the client also shows a strategy picker;
otherwise strategies are assigned automatically.

## Tests

```bash
pytest                          # runs everything
pytest tests/test_routes.py     # run a specific test file
```

- `test_blender.py` — weighted fusion, normalisation, novelty, rationale arithmetic
- `test_integration.py` — the `/recommend` pipeline end to end over HTTP
- `test_routes.py` — supporting routes, mood analysis and JWT admin
- `test_adapter.py` — collaborative adapter parsing and caching
- `test_lyric_signal.py` — lyric fetching, sentiment scoring and cache behaviour
- `test_ab_switch.py` — strategy assignment with A/B testing on and off
- `test_variants_freeze.py` — pins the variant weights and assignments used by the study
The suite needs no network access and no API keys, as the external services are
replaced with recorded fixtures.

## Evaluation

Index accuracy and latency, approximate versus exact search:

```bash
python eval.py
```

Variant benchmark over 40 seed tracks across 4 genres:

```bash
python -m benchmarks.benchmark   # -m is required: the benchmark is a package that imports from the project root
```

The benchmark compares every A/B variant against a random control on coherence,
diversity, popularity coverage and lyric coverage, with Wilcoxon signed-rank
tests paired per seed. It also sweeps the novelty parameter and the mood
settings. Results are saved to `benchmarks/benchmark_results.json` and
`benchmarks/benchmark_mood.json`.

Because the lyrics are fetched from LRCLIB, the first run takes a while;
everything is cached in `data/lyrics_cache` afterwards. Set `LASTFM_API_KEY`
before running, or the collaborative columns will be empty.

### Rating study

The evaluation plan called for two rounds of user testing. Participants were not
recruited within the project timeline, so the rounds were replaced by a
simulated study. **The raters are synthetic** — their preferences are rules
defined in `studies/sim_study.py`, so the results describe those rules rather
than human listeners. What the simulation does establish is that the experiment
infrastructure works end to end, and what sample size a real study would need.

```bash
# the API must be running, with AB_TESTING=true
python -m studies.sim_study --raters 30 --seeds 4
python -m studies.analyse_study --experiment "simulated round 1"
python -m studies.power_analysis
```

`analyse_study.py` works identically on real participant ratings; nothing in it
knows how the data was produced. `power_analysis.py` takes the observed
between-rater variance and reports how many participants a real study would need
to detect a difference of a given size.

## API

| Area | Endpoints |
| --- | --- |
| Recommendations | `POST /recommend`, `POST /recommend/similar`, `POST /onboard` |
| Mood | `POST /mood/analyse`, `POST /mood/recommend` |
| Tracks | `GET /tracks/search`, `GET /tracks/{id}/info`, `GET /tracks/{id}/features` |
| Experiments | `GET /experiments/{name}/variant`, `POST /experiments/{name}/metrics`, `POST /feedback` |
| Admin (JWT) | `POST /auth/login`, `GET /admin/stats`, `GET /admin/health` |
| Other | `GET /health` |

### Example

```bash
curl -X POST http://127.0.0.1:8000/recommend \
    -H "Content-Type: application/json" \
    -d '{
            "seed_tracks": ["7lmeHLHBe4nmXzuXc0HDjk"],
            "limit": 5,
            "parameters": {"novelty": 0.5, "target_mood": "calm"}
        }'
```

All recommendations are returned with a `rationale` giving each signal's
contribution and each preference's penalty. These sum to the track's score, so
the ranking is always explainable — a track with a weaker audio match can
outrank a stronger one, and the rationale shows why.

Use `GET /tracks/search?q=...` to find seed IDs. Recommendation is a POST
because it carries a request body.

## Notes and limitations

- **Catalogue coverage** — the dataset is only a snapshot and omits many
artists, so some Last.fm suggestions cannot be matched to a track and are
dropped. A small number of IDs no longer resolve on Spotify either, and the
embedded player shows those as unavailable.
- **Matching** — Last.fm and LRCLIB are both matched on artist and title after
normalisation, which is lossy: featured artists and alternative titles can
miss.
- **Mood** — derived from the audio features valence and energy, so several
moods can be missed. The lyric signal addresses sentiment, but energetic
versus calm remains audio-derived.
- **Copyright** — lyrics fetched for scoring are never stored or returned. Only
the resulting sentiment score is cached.
