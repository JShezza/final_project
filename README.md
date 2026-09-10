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
