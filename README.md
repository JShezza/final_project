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
