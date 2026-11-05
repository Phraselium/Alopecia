import sys
from pathlib import Path

import pytest
import yaml

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))


@pytest.fixture
def cfg():
    return yaml.safe_load((BASE / "config.yaml").read_text(encoding="utf-8"))


@pytest.fixture
def fiscal():
    return yaml.safe_load((BASE / "fiscal.yaml").read_text(encoding="utf-8"))


@pytest.fixture
def rel():
    return yaml.safe_load((BASE / "reliability.yaml").read_text(encoding="utf-8"))
