"""
benchmark.py

offline variant benchmark

ruyn every A/B variant over a fixed set of seed tracks (40 tracks, 4 genres)
Comapres the top 10 output  on three metrics, coherence, diversity (pairwise distance mean),
novelty (mean log playcount of recommended tracks that have last.fm data)

compared per seed with Wilcoxon signed ranked tests

collab signial is read cache first run with a lastfm api key
"""

from blender import (
    VARIANTS,
    Blender,
    catalogue_lookup,
    collaborative_pool,
    normalise_title,
)
from recommender import Recommender
