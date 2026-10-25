import json
from pathlib import Path
from datetime import datetime, timezone
from valutatrade_hub.core.exceptions import CurrencyNotFoundError

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
    path.write_text(
        json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def read_dict(path: Path) -> dict:
    """Для rates.json: словарь вида {"EUR_USD": {"rate": ...}, ...}."""
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def write_dict(path: Path, data: dict) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# --- валидация кода валюты ---
def normalize_currency_code(code: str) -> str:
    """Валидирует и нормализует код валюты: непустая строка, верхний регистр, 2-5 символов, без пробелов."""
    if not isinstance(code, str):
        raise CurrencyNotFoundError(code)
    normalized = code.strip().upper()
    if not normalized or not (2 <= len(normalized) <= 5) or " " in normalized:
        raise CurrencyNotFoundError(code)
    return normalized


# --- валидация сумм ---
def validate_amount(value) -> float:
    """Проверяет, что amount — положительное число. Иначе ValueError с сообщением из ТЗ."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("'amount' должен быть положительным числом")
    if value <= 0:
        raise ValueError("'amount' должен быть положительным числом")
    return float(value)


# --- конвертация ---
def convert_currency(amount: float, rate_from: float, rate_to: float) -> float:
    """Конвертация через USD: usd = amount * rate_from; result = usd / rate_to.

    rate_from / rate_to — сколько USD стоит 1 единица соответствующей валюты.
    """
    if rate_to == 0:
        raise ValueError("Нулевой курс целевой валюты.")
    return (amount * rate_from) / rate_to


# --- форматирование ---
def format_amount(value: float, currency_code: str) -> str:
    """Криптовалюты — 4 знака после запятой, фиат — 2 (как в примерах ТЗ)."""
    if currency_code in {"BTC", "ETH"}:
        return f"{value:.4f}"
    return f"{value:.2f}"


def format_money(value: float) -> str:
    """Сумма с разделителем тысяч: 3329 -> 3,329.00"""
    return f"{value:,.2f}"


def iso_now() -> str:
    """Текущее время в ISO (UTC)."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
