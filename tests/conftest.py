"""pytest 公共配置：把项目根目录加入 sys.path，并提供常用 fixture。"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture
def data_dir() -> Path:
    return ROOT / "data"