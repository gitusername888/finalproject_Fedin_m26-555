"""Бизнес-логика ValutaTrade Hub.

CLI не дублирует логику — все операции идут через функции этого модуля.
"""
"""Бизнес-логика: register/login, get-rate, buy/sell, портфель.

Курсы получают из кеша data/rates.json (DatabaseManager) с TTL из
SettingsLoader; при устаревании кеш обновляется заглушкой Parser Service.
Все валютные коды валидируются через currencies.get_currency().
"""
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from valutatrade_hub.core.currencies import get_currency
from valutatrade_hub.core.exceptions import ApiRequestError, CurrencyNotFoundError
from valutatrade_hub.core.models import Portfolio, User
from valutatrade_hub.core.utils import iso_now, validate_amount
from valutatrade_hub.decorators import log_action
from valutatrade_hub.infra.database import DatabaseManager
from valutatrade_hub.infra.settings import SettingsLoader

settings = SettingsLoader()
db = DatabaseManager()


# ======================= ЗАГЛУШКА Parser Service =======================
# Пока Parser Service не подключён. При подключении заменить refresh_rates()
# на реальный запрос к API; контракт rates.json уже соответствует ТЗ.
STUB_RATES: Dict[str, float] = {
    "EUR_USD": 1.0786,
    "BTC_USD": 59337.21,
    "RUB_USD": 0.01016,
    "ETH_USD": 3720.00,
}


def refresh_rates() -> None:
    """Обновляет кеш rates.json данными заглушки Parser Service."""
    now = iso_now()
    payload: Dict[str, Any] = {
        pair: {"rate": rate, "updated_at": now} for pair, rate in STUB_RATES.items()
    }
    payload["source"] = "ParserService"
    payload["last_refresh"] = now
    db.save("rates", payload)


def _read_rates() -> Dict[str, Any]:
    return db.load("rates", dict) or {}


def _is_stale(rates: Dict[str, Any]) -> bool:
    ttl = int(settings.get("rates_ttl_seconds", 300))
    last_refresh = rates.get("last_refresh")
    if not last_refresh:
        return True
    try:
        updated = datetime.fromisoformat(last_refresh)
    except ValueError:
        return True
    return datetime.now(timezone.utc) - updated > timedelta(seconds=ttl)


def ensure_fresh_rates() -> Dict[str, Any]:
    """Возвращает свежий кеш курсов: устарел — обновляет заглушкой."""
    rates = _read_rates()
    if _is_stale(rates):
        refresh_rates()
        rates = _read_rates()
    return rates


def _usd_per_unit(code: str, rates: Dict[str, Any]) -> float:
    """Сколько USD стоит 1 единица валюты code."""
    if code == "USD":
        return 1.0
    entry = rates.get(f"{code}_USD")
    if not entry:
        raise ApiRequestError(f"нет курса {code}/USD")
    return float(entry["rate"])


# ======================= Курс валют =======================
def get_rate(from_code: str, to_code: str) -> Dict[str, Any]:
    """Возвращает {"rate": float, "updated_at": str} для пары from -> to.

    Валидация кодов — через get_currency() (CurrencyNotFoundError).
    Кеш с TTL из SettingsLoader; если обновление не дало пару — ApiRequestError.
    """
    src = get_currency(from_code)   # CurrencyNotFoundError для неизвестного кода
    dst = get_currency(to_code)

    rates = ensure_fresh_rates()
    if not rates:
        raise ApiRequestError("нет данных о курсах")

    usd_src = _usd_per_unit(src.code, rates)
    usd_dst = _usd_per_unit(dst.code, rates)

    if src.code == dst.code:
        rate = 1.0
        updated_at = rates.get("last_refresh", iso_now())
    else:
        rate = usd_src / usd_dst
        pair_entry = rates.get(f"{src.code}_{dst.code}") or rates.get(f"{dst.code}_{src.code}")
        updated_at = pair_entry["updated_at"] if pair_entry else rates.get("last_refresh", iso_now())

    return {"rate": rate, "updated_at": updated_at, "source": rates.get("source", "-")}


# ======================= Пользователи =======================
@log_action("REGISTER")
def register_user(username: str, password: str) -> User:
    users = db.load("users", list) or []
    if any(u["username"] == username for u in users):
        raise ValueError(f"Имя пользователя '{username}' уже занято")

    user = User(user_id=max((u["user_id"] for u in users), default=0) + 1,
                username=username, password=password)
    users.append(user.to_dict())
    db.save("users", users)

    # Пустой портфель при регистрации
    portfolios = db.load("portfolios", list) or []
    portfolios.append({"user_id": user.user_id, "wallets": {}})
    db.save("portfolios", portfolios)
    return user


@log_action("LOGIN")
def login_user(username: str, password: str) -> User:
    users = db.load("users", list) or []
    record = next((u for u in users if u["username"] == username), None)
    if record is None:
        raise ValueError(f"Пользователь '{username}' не найден")
    user = User.from_record(record)
    if not user.check_password(password):
        raise ValueError("Неверный пароль")
    return user


# ======================= Портфель =======================
def load_portfolio(user: User) -> Portfolio:
    portfolios = db.load("portfolios", list) or []
    record = next((p for p in portfolios if p["user_id"] == user.user_id), None)
    if record is None:
        record = {"user_id": user.user_id, "wallets": {}}
        portfolios.append(record)
        db.save("portfolios", portfolios)
    return Portfolio.from_record(user, record)


def save_portfolio(portfolio: Portfolio) -> None:
    portfolios = db.load("portfolios", list) or []
    record = portfolio.to_record()
    for i, p in enumerate(portfolios):
        if p["user_id"] == record["user_id"]:
            portfolios[i] = record
            break
    else:
        portfolios.append(record)
    db.save("portfolios", portfolios)


def get_portfolio_summary(user: User, base_currency: str = "USD") -> Dict[str, Any]:
    """Сводка портфеля: строки по кошелькам + ИТОГО в базовой валюте."""
    base = get_currency(base_currency)  # CurrencyNotFoundError для неизвестной базы
    rates = ensure_fresh_rates()
    portfolio = load_portfolio(user)

    rows = []
    total = 0.0
    for code, wallet in portfolio.wallets.items():
        usd_per_unit = _usd_per_unit(code, rates)
        value_in_base = wallet.balance * usd_per_unit / _usd_per_unit(base.code, rates)
        total += value_in_base
        rows.append({
            "code": code,
            "balance": wallet.balance,
            "value_in_base": value_in_base,
        })
    return {"rows": rows, "total": total, "base": base.code, "source": rates.get("source", "-")}


# ======================= Торговля =======================
@log_action("BUY")
def buy_currency(user: User, currency_code: str, amount: float) -> Dict[str, Any]:
    """Покупка валюты за USD: списание с USD-кошелька, зачисление amount валюты."""
    currency = get_currency(currency_code)      # CurrencyNotFoundError
    amt = validate_amount(amount)               # ValueError при некорректной сумме

    rates = ensure_fresh_rates()
    rate = _usd_per_unit(currency.code, rates)  # ApiRequestError при отсутствии курса
    cost_usd = amt * rate

    portfolio = load_portfolio(user)
    usd_wallet = portfolio.wallets.get("USD") or portfolio.add_currency("USD")

    was = portfolio.wallets.get(currency.code).balance if currency.code in portfolio.wallets else 0.0
    usd_wallet.withdraw(cost_usd)               # InsufficientFundsError при нехватке
    wallet = (portfolio.wallets.get(currency.code) if currency.code in portfolio.wallets
              else portfolio.add_currency(currency.code))
    wallet.deposit(amt)
    save_portfolio(portfolio)

    return {
        "rate": rate, "base": "USD", "cost": cost_usd,
        "was": was, "became": wallet.balance,
    }


@log_action("SELL")
def sell_currency(user: User, currency_code: str, amount: float) -> Dict[str, Any]:
    """Продажа валюты: списание с кошелька валюты, зачисление выручки в USD."""
    currency = get_currency(currency_code)
    amt = validate_amount(amount)

    rates = ensure_fresh_rates()
    rate = _usd_per_unit(currency.code, rates)
    proceeds_usd = amt * rate

    portfolio = load_portfolio(user)
    wallet = portfolio.get_wallet(currency.code)   # KeyError -> сообщение про кошелёк
    was = wallet.balance
    wallet.withdraw(amt)                           # InsufficientFundsError при нехватке

    usd_wallet = portfolio.wallets.get("USD") or portfolio.add_currency("USD")
    usd_wallet.deposit(proceeds_usd)
    save_portfolio(portfolio)

    return {
        "rate": rate, "base": "USD", "proceeds": proceeds_usd,
        "was": was, "became": wallet.balance,
    }
