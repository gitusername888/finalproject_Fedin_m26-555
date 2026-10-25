"""Бизнес-логика ValutaTrade Hub.

CLI не дублирует логику — все операции идут через функции этого модуля.
"""

import re
from datetime import datetime, timedelta, timezone
from typing import Tuple

from valutatrade_hub.core.models import User, Wallet, Portfolio
from valutatrade_hub.core.utils import (
    USERS_FILE, PORTFOLIO_FILE, RATES_FILE,
    read_list, write_list, read_dict, write_dict,
)

FRESH_MINUTES = 5  # курс считается свежим, если моложе 5 минут
CURRENCY_RE = re.compile(r"^[A-Z]{2,5}$")

# Заглушка курсов (пока не подключён Parser Service): сколько USD стоит 1 единица валюты.
STUB_RATES = {
    "EUR_USD": 1.0786,
    "BTC_USD": 59337.21,
    "RUB_USD": 0.01016,
    "ETH_USD": 3720.00,
}
STUB_SOURCE = "StubService"


class UsecaseError(Exception):
    """Ошибка бизнес-логики с сообщением для пользователя."""


def fmt_amount(code: str, value: float) -> str:
    """Формат суммы: 2 знака для фиата, 4 — для криптовалют."""
    if code in ("USD", "EUR", "RUB"):
        return f"{value:,.2f}"
    return f"{value:.4f}"


def validate_currency(code) -> str:
    if not isinstance(code, str):
        raise UsecaseError("Код валюты должен быть непустой строкой.")
    code = code.strip().upper()
    if not CURRENCY_RE.match(code):
        raise UsecaseError(
            f"Некорректный код валюты '{code}'. Ожидается 2–5 заглавных латинских букв."
        )
    return code


def validate_amount(raw) -> float:
    if isinstance(raw, bool):
        raise UsecaseError("'amount' должен быть положительным числом")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise UsecaseError("'amount' должен быть положительным числом")
    if value <= 0:
        raise UsecaseError("'amount' должен быть положительным числом")
    return value


# ---------------- курсы валют ----------------

def _pair_time(pair: dict) -> datetime:
    return datetime.fromisoformat(pair["updated_at"])


def _load_rates() -> dict:
    data = read_dict(RATES_FILE)
    return {k: v for k, v in data.items() if k not in ("source", "last_refresh")}


def refresh_rates_if_stale(rates: dict) -> dict:
    """Обновляет устаревшие (старше 5 минут) пары из заглушки и пишет кеш на диск."""
    now = datetime.now(timezone.utc)
    changed = False
    for key, stub_rate in STUB_RATES.items():
        pair = rates.get(key)
        fresh = False
        if pair:
            try:
                fresh = (now - _pair_time(pair)) < timedelta(minutes=FRESH_MINUTES)
            except (KeyError, ValueError):
                fresh = False
        if not fresh:
            rates[key] = {"rate": stub_rate, "updated_at": now.isoformat()}
            changed = True
    if changed:
        rates["source"] = STUB_SOURCE
        rates["last_refresh"] = now.isoformat()
        write_dict(RATES_FILE, rates)
    return rates


def get_rate(from_currency: str, to_currency: str) -> Tuple[float, datetime]:
    """Возвращает (курс FROM→TO, время обновления) из кеша rates.json или заглушки."""
    f = validate_currency(from_currency)
    t = validate_currency(to_currency)
    rates = refresh_rates_if_stale(_load_rates())

    if f == t:
        return 1.0, datetime.now(timezone.utc)

    def usd_rate(code: str) -> float:
        pair = rates.get(f"{code}_USD")
        if pair is None:
            raise KeyError(code)
        return float(pair["rate"])

    try:
        if t == "USD":
            rate = usd_rate(f)
        elif f == "USD":
            rate = 1.0 / usd_rate(t)
        else:
            rate = usd_rate(f) / usd_rate(t)
    except KeyError:
        raise UsecaseError(f"Курс {f}→{t} недоступен. Повторите попытку позже.")

    updated = rates.get(f"{t}_USD") or rates.get(f"{f}_USD")
    when = _pair_time(updated) if updated else datetime.now(timezone.utc)
    return rate, when


# ---------------- пользователи ----------------

def register_user(username: str, password: str) -> User:
    users = read_list(USERS_FILE)
    if any(u.get("username") == username for u in users):
        raise UsecaseError(f"Имя пользователя '{username}' уже занято")

    try:
        user = User(
            user_id=max((u.get("user_id", 0) for u in users), default=0) + 1,
            username=username,
            password=password,  # внутри валидация длины + хеширование с солью
        )
    except ValueError as e:
        # ошибки валидации моделей превращаем в понятное сообщение для CLI
        raise UsecaseError(str(e))
    users.append(user.to_dict())
    write_list(USERS_FILE, users)

    # пустой портфель
    portfolios = read_list(PORTFOLIO_FILE)
    portfolios.append({"user_id": user.user_id, "wallets": {}})
    write_list(PORTFOLIO_FILE, portfolios)
    return user


def login_user(username: str, password: str) -> User:
    for record in read_list(USERS_FILE):
        if record.get("username") == username:
            user = User.from_record(record)
            if not user.check_password(password):
                raise UsecaseError("Неверный пароль")
            return user
    raise UsecaseError(f"Пользователь '{username}' не найден")


# ---------------- портфель ----------------

def load_portfolio(user: User) -> Portfolio:
    for record in read_list(PORTFOLIO_FILE):
        if record.get("user_id") == user.user_id:
            return Portfolio.from_record(user, record)
    portfolio = Portfolio(user)
    save_portfolio(portfolio)
    return portfolio


def save_portfolio(portfolio: Portfolio) -> None:
    portfolios = read_list(PORTFOLIO_FILE)
    record = portfolio.to_record()
    for i, p in enumerate(portfolios):
        if p.get("user_id") == portfolio.user_id:
            portfolios[i] = record
            break
    else:
        portfolios.append(record)
    write_list(PORTFOLIO_FILE, portfolios)


def get_portfolio_overview(user: User, base: str = "USD") -> dict:
    """Данные для show-portfolio: строки по кошелькам + итог в base."""
    base = validate_currency(base)
    rates = refresh_rates_if_stale(_load_rates())
    if base != "USD" and f"{base}_USD" not in rates:
        raise UsecaseError(f"Неизвестная базовая валюта '{base}'")

    portfolio = load_portfolio(user)
    if not portfolio.wallets:
        raise UsecaseError("Портфель пуст — кошельков пока нет. Купите валюту командой buy.")

    base_usd_rate = 1.0 if base == "USD" else float(rates[f"{base}_USD"]["rate"])
    rows, total_usd = [], 0.0
    for code, wallet in portfolio.wallets.items():
        balance = wallet.balance
        usd_value = balance if code == "USD" else balance * float(rates[f"{code}_USD"]["rate"])
        total_usd += usd_value
        rows.append((code, balance, usd_value / base_usd_rate))
    return {"rows": rows, "total": total_usd / base_usd_rate, "base": base}


# ---------------- торговые операции ----------------

def buy_currency(user: User, currency: str, amount_raw) -> dict:
    """Покупка валюты за USD: списание с USD-кошелька, начисление на кошелёк валюты."""
    code = validate_currency(currency)
    amount = validate_amount(amount_raw)
    if code == "USD":
        raise UsecaseError("Покупать USD нет смысла — это базовая валюта портфеля.")

    rates = refresh_rates_if_stale(_load_rates())
    pair = rates.get(f"{code}_USD")
    if pair is None:
        raise UsecaseError(f"Не удалось получить курс для {code}→USD")
    rate = float(pair["rate"])

    portfolio = load_portfolio(user)
    usd_wallet = portfolio.wallets.get("USD")
    cost = amount * rate
    if usd_wallet is None or usd_wallet.balance < cost:
        available = usd_wallet.balance if usd_wallet else 0.0
        raise UsecaseError(
            f"Недостаточно средств: доступно {fmt_amount('USD', available)} USD, "
            f"требуется {fmt_amount('USD', cost)} USD."
        )

    if code not in portfolio.wallets:
        portfolio.add_currency(code)  # автоматическое создание кошелька
    before = portfolio.get_wallet(code).balance
    portfolio.get_wallet(code).deposit(amount)
    portfolio.get_wallet("USD").withdraw(cost)
    save_portfolio(portfolio)

    return {"code": code, "amount": amount, "rate": rate,
            "before": before, "after": before + amount, "cost": cost}


def sell_currency(user: User, currency: str, amount_raw) -> dict:
    """Продажа валюты: списание с кошелька валюты, начисление выручки на USD-кошелёк."""
    code = validate_currency(currency)
    amount = validate_amount(amount_raw)
    if code == "USD":
        raise UsecaseError("Продавать USD нет смысла — это базовая валюта портфеля.")

    rates = refresh_rates_if_stale(_load_rates())
    pair = rates.get(f"{code}_USD")
    if pair is None:
        raise UsecaseError(f"Не удалось получить курс для {code}→USD")
    rate = float(pair["rate"])

    portfolio = load_portfolio(user)
    if code not in portfolio.wallets:
        raise UsecaseError(
            f"У вас нет кошелька '{code}'. Добавьте валюту: она создаётся автоматически при первой покупке."
        )

    before = portfolio.get_wallet(code).balance
    if amount > before:
        raise UsecaseError(
            f"Недостаточно средств: доступно {fmt_amount(code, before)} {code}, "
            f"требуется {fmt_amount(code, amount)} {code}"
        )

    portfolio.get_wallet(code).withdraw(amount)
    proceeds = amount * rate
    if "USD" not in portfolio.wallets:
        portfolio.add_currency("USD")
    portfolio.get_wallet("USD").deposit(proceeds)
    save_portfolio(portfolio)

    return {"code": code, "amount": amount, "rate": rate,
            "before": before, "after": before - amount, "proceeds": proceeds}