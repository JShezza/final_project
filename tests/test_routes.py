"""
test_routes.py

tests for supporting routes: similar, onboard, mood analyse/recommend
"""

import json
import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("ADMIN_USERNAME", "admin")
os.environ.setdefault("ADMIN_PASSWORD", "password")
os.environ.setdefault("JWT_SECRET", "test-secret-string")

import main  # noqa: E402

SEED = "7lmeHLHBe4nmXzuXc0HDjk"


@pytest.fixture(scope="module")
def client():
    return TestClient(main.app)
