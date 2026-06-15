# -*- coding: utf-8 -*-
"""Shared pytest fixtures. Makes the rgt_dashboard package importable when
pytest is run from the RGT_APP/ directory and loads the DataStore once."""
import os
import sys

import pytest

# RGT_APP/ (one level up from tests/) so `import rgt_dashboard` works.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(scope="session")
def store():
    from rgt_dashboard.data import get_store
    return get_store()
