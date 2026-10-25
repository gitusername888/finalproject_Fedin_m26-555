"""CLI ValutaTrade Hub. Единственная точка входа для команд.

interface.py тонкий: только разбор аргументов и печать; вся бизнес-логика — в usecases.
"""
from valutatrade_hub.core import usecases
from valutatrade_hub.core.currencies import CurrencyRegistry
from valutatrade_hub.core.exceptions import (
    ApiRequestError,
    CurrencyNotFoundError,
    InsufficientFundsError,
)
from valutatrade_hub.core.utils import format_amount, format_money
from valutatrade_hub.logging_config import setup_logging

session = {"user": None}


def _get(tokens: list, flag: str) -> str | None:
    if flag in tokens:
        i = tokens.index(flag)
        if i + 1 < len(tokens):
            return tokens[i + 1]
    return None


def cmd_register(tokens: list) -> None:
    username, password = _get(tokens, "--username"), _get(tokens, "--password")
    if not username or not password:
        print("Использование: register --username <имя> --password <пароль>")
        return
    try:
        user = usecases.register_user(username, password)
    except ValueError as e:
        print(e)
        return
    print(f"Пользователь '{user.username}' зарегистрирован (id={user.user_id}). "
          f"Войдите: login --username {user.username} --password ****")


def cmd_login(tokens: list) -> None:
    username, password = _get(tokens, "--username"), _get(tokens, "--password")
    if not username or not password:
        print("Использование: login --username <имя> --password <пароль>")
        return
    try:
        user = usecases.login_user(username, password)
    except ValueError as e:
        print(e)
        return
    session["user"] = user
    print(f"Вы вошли как '{user.username}'")


def cmd_show_portfolio(tokens: list) -> None:
    if session["user"] is None:
        print("Сначала выполните login")
        return
    base = _get(tokens, "--base") or usecases.settings.get("default_base_currency", "USD")
    try:
        summary = usecases.get_portfolio_summary(session["user"], base)
    except CurrencyNotFoundError as e:
        print(f"{e} Поддерживаемые коды: {', '.join(CurrencyRegistry.supported_codes())}")
        return
    if not summary["rows"]:
        print("Портфель пуст — кошельков ещё нет.")
        return
    print(f"Портфель пользователя '{session['user'].username}' (база: {summary['base']}):")
    for row in summary["rows"]:
        print(f"- {row['code']}: {format_amount(row['balance'], row['code'])}  "
              f"→ {format_money(row['value_in_base'])} {summary['base']}")
    print("-" * 33)
    print(f"ИТОГО: {format_money(summary['total'])} {summary['base']}")


def _parse_amount(raw: str | None):
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        print("'amount' должен быть положительным числом")
        return None


def cmd_buy(tokens: list) -> None:
    if session["user"] is None:
        print("Сначала выполните login")
        return
    currency, amount = _get(tokens, "--currency"), _parse_amount(_get(tokens, "--amount"))
    if not currency or amount is None:
        print("Использование: buy --currency <код> --amount <сумма>")
        return
    try:
        result = usecases.buy_currency(session["user"], currency, amount)
    except (InsufficientFundsError, ApiRequestError) as e:
        print(e)
        return
    except CurrencyNotFoundError as e:
        print(f"{e} Поддерживаемые коды: {', '.join(CurrencyRegistry.supported_codes())}")
        return
    except ValueError as e:
        print(f"Ошибка: {e}")
        return
    code = currency.upper()
    print(f"Покупка выполнена: {format_amount(amount, code)} {code} "
          f"по курсу {format_money(result['rate'])} USD/{code}")
    print("Изменения в портфеле:")
    print(f"- {code}: было {format_amount(result['was'], code)} → "
          f"стало {format_amount(result['became'], code)}")
    print(f"Оценочная стоимость покупки: {format_money(result['cost'])} USD")


def cmd_sell(tokens: list) -> None:
    if session["user"] is None:
        print("Сначала выполните login")
        return
    currency, amount = _get(tokens, "--currency"), _parse_amount(_get(tokens, "--amount"))
    if not currency or amount is None:
        print("Использование: sell --currency <код> --amount <сумма>")
        return
    try:
        result = usecases.sell_currency(session["user"], currency, amount)
    except InsufficientFundsError as e:
        print(e)
        return
    except ApiRequestError as e:
        print(e)
        return
    except CurrencyNotFoundError as e:
        print(f"{e} Поддерживаемые коды: {', '.join(CurrencyRegistry.supported_codes())}")
        return
    except KeyError as e:
        print(e.args[0])
        return
    except ValueError as e:
        print(f"Ошибка: {e}")
        return
    code = currency.upper()
    print(f"Продажа выполнена: {format_amount(amount, code)} {code} "
          f"по курсу {format_money(result['rate'])} USD/{code}")
    print("Изменения в портфеле:")
    print(f"- {code}: было {format_amount(result['was'], code)} → "
          f"стало {format_amount(result['became'], code)}")
    print(f"Оценочная выручка: {format_money(result['proceeds'])} USD")


def cmd_get_rate(tokens: list) -> None:
    from_code, to_code = _get(tokens, "--from"), _get(tokens, "--to")
    if not from_code or not to_code:
        print("Использование: get-rate --from <код> --to <код>")
        return
    try:
        data = usecases.get_rate(from_code, to_code)
    except CurrencyNotFoundError:
        raise  # перехватываем в run() — там печатаем список поддерживаемых кодов
    except ApiRequestError as e:
        print(f"{e}. Повторите попытку позже или проверьте сеть.")
        return
    ts = data["updated_at"].replace("T", " ").split(".")[0]
    print(f"Курс {from_code.upper()}→{to_code.upper()}: {data['rate']:.8f} (обновлено: {ts})")
    print(f"Обратный курс {to_code.upper()}→{from_code.upper()}: {1 / data['rate']:.2f}")


COMMANDS = {
    "register": cmd_register,
    "login": cmd_login,
    "show-portfolio": cmd_show_portfolio,
    "buy": cmd_buy,
    "sell": cmd_sell,
    "get-rate": cmd_get_rate,
    "help": lambda _: print(
        "Доступные команды:\n"
        "  register --username <имя> --password <пароль>\n"
        "  login --username <имя> --password <пароль>\n"
        "  show-portfolio [--base <код>]\n"
        "  buy --currency <код> --amount <сумма>\n"
        "  sell --currency <код> --amount <сумма>\n"
        "  get-rate --from <код> --to <код>\n"
        "  exit — выход"
    ),
}


def run() -> None:
    setup_logging()
    print("ValutaTrade Hub. Введите 'help' для списка команд.")
    while True:
        try:
            raw = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nВыход.")
            break
        if not raw:
            continue
        parts = raw.split()
        cmd, tokens = parts[0].lower(), parts[1:]
        if cmd in ("exit", "quit"):
            break
        handler = COMMANDS.get(cmd)
        if not handler:
            print(f"Неизвестная команда: {cmd}. Введите 'help'.")
            continue
        try:
            handler(tokens)
        except CurrencyNotFoundError as e:
            print(f"{e} Поддерживаемые коды: {', '.join(CurrencyRegistry.supported_codes())}")
        except ApiRequestError as e:
            print(f"{e}. Повторите попытку позже или проверьте сеть.")
        except (InsufficientFundsError, ValueError, KeyError) as e:
            print(e)
