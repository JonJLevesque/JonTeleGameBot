import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")

import pytest

import db as _dbmod


@pytest.fixture()
def db():
    """Fresh in-memory database per test."""
    _dbmod.init(":memory:")
    yield _dbmod
    _dbmod._conn.close()
    _dbmod._conn = None


class FakeUser:
    def __init__(self, uid, name):
        self.id, self.first_name = uid, name
        self.username, self.is_bot = name.lower(), False
