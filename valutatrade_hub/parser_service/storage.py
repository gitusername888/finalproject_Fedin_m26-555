
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # корень проекта
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

USERS_FILE = DATA_DIR / "users.json"
PORTFOLIO_FILE = DATA_DIR / "portfolios.json"
RATES_FILE = DATA_DIR / "rates.json"


def _ensure_list_file(path: Path) -> None:
    if not path.exists():
        path.write_text("[]", encoding="utf-8")


def read_list(path: Path) -> list:
    _ensure_list_file(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else []


def write_list(path: Path, items: list) -> None:
    _ensure_list_file(path)
    path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def read_dict(path: Path) -> dict:
    """Для rates.json: словарь пар курсов + служебные ключи."""
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def write_dict(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
