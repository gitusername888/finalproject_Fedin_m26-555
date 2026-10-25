
"""CLI ValutaTrade Hub — единственная точка входа для пользовательских команд.

Здесь только разбор аргументов и вывод: бизнес-логика живёт в core/usecases.py.
"""

from valutatrade_hub.core import usecases
from valutatrade_hub.core.models import User

# Текущая сессия (в рамках одного запуска процесса)
session: dict = {"user": None}


def _require_login() -> User:
    if session["user"] is None:
        raise usecases.UsecaseError("Сначала выполните login")
    return session["user"]


def _parse_args(tokens: list) -> dict:
    """Разбор флагов вида --key value."""
    parsed, i = {}, 0
    while i < len(tokens):
        token = tokens[i]
        if token.startswith("--"):
            key = token[2:]
            if i + 1 >= len(tokens):
                raise usecases.UsecaseError(f"Не указано значение для --{key}")
            parsed[key] = tokens[i + 1]
            i += 2
        else:
            i += 1
    return parsed


def _get(args: dict, key: str) -> str:
    if key not in args:
        raise usecases.UsecaseError(f"Укажите обязательный аргумент --{key}")
    return args[key]


# ---------------- команды ----------------

def cmd_register(tokens: list) -> None:
    args = _parse_args(tokens)
    try:
        user = usecases.register_user(_get(args, "username"), _get(args, "password"))
    except usecases.UsecaseError as e:
        print(e)
        return
    print(
        f"Пользователь '{user.username}' зарегистрирован (id={user.user_id}). "
        f"Войдите: login --username {user.username} --password ****"
    )


def cmd_login(tokens: list) -> None:
    args = _parse_args(tokens)
    try:
        user = usecases.login_user(_get(args, "username"), _get(args, "password"))
    except usecases.UsecaseError as e:
        print(e)
        return
    session["user"] = user
    print(f"Вы вошли как '{user.username}'")


def cmd_show_portfolio(tokens: list) -> None:
    args = _parse_args(tokens)
    try:
        user = _require_login()
        overview = usecases.get_portfolio_overview(user, args.get("base", "USD"))
    except usecases.UsecaseError as e:
        print(e)
        return
    print(f"Портфель пользователя '{user.username}' (база: {overview['base']}):")
    for code, balance, value in overview["rows"]:
        print(f"- {code}: {usecases.fmt_amount(code, balance)}  →  {value:,.2f} {overview['base']}")
    print("-" * 33)
    print(f"ИТОГО: {overview['total']:,.2f} {overview['base']}")


def cmd_buy(tokens: list) -> None:
    args = _parse_args(tokens)
    try:
        user = _require_login()
        r = usecases.buy_currency(user, _get(args, "currency"), _get(args, "amount"))
    except usecases.UsecaseError as e:
        print(e)
        return
    print(f"Покупка выполнена: {r['amount']:.4f} {r['code']} по курсу {r['rate']:.2f} USD/{r['code']}")
    print("Изменения в портфеле:")
    print(f"- {r['code']}: было {usecases.fmt_amount(r['code'], r['before'])} "
          f"→ стало {usecases.fmt_amount(r['code'], r['after'])}")
    print(f"Оценочная стоимость покупки: {r['cost']:,.2f} USD")


def cmd_sell(tokens: list) -> None:
    args = _parse_args(tokens)
    try:
        user = _require_login()
        r = usecases.sell_currency(user, _get(args, "currency"), _get(args, "amount"))
    except usecases.UsecaseError as e:
        print(e)
        return
    print(f"Продажа выполнена: {r['amount']:.4f} {r['code']} по курсу {r['rate']:.2f} USD/{r['code']}")
    print("Изменения в портфеле:")
    print(f"- {r['code']}: было {usecases.fmt_amount(r['code'], r['before'])} "
          f"→ стало {usecases.fmt_amount(r['code'], r['after'])}")
    print(f"Оценочная выручка: {r['proceeds']:,.2f} USD")


def cmd_get_rate(tokens: list) -> None:
    args = _parse_args(tokens)
    f, t = args.get("from", ""), args.get("to", "")
    try:
        rate, when = usecases.get_rate(_get(args, "from"), _get(args, "to"))
    except usecases.UsecaseError as e:
        print(e)
        return
    stamp = when.strftime("%Y-%m-%d %H:%M:%S")
    print(f"Курс {f.upper()}→{t.upper()}: {rate:.8f} (обновлено: {stamp})")
    if rate:
        print(f"Обратный курс {t.upper()}→{f.upper()}: {1 / rate:.2f}")


def cmd_logout(_: list) -> None:
    if session["user"] is None:
        print("Вы и так не вошли.")
        return
    print(f"Вы вышли из аккаунта '{session['user'].username}'.")
    session["user"] = None


def cmd_help(_: list) -> None:
    print(
        "Доступные команды:\n"
        "  register --username <имя> --password <пароль>\n"
        "  login --username <имя> --password <пароль>\n"
        "  logout\n"
        "  show-portfolio [--base USD]\n"
        "  buy --currency <код> --amount <число>\n"
        "  sell --currency <код> --amount <число>\n"
        "  get-rate --from <код> --to <код>\n"
        "  help | exit"
    )


COMMANDS = {
    "register": cmd_register,
    "login": cmd_login,
    "logout": cmd_logout,
    "show-portfolio": cmd_show_portfolio,
    "buy": cmd_buy,
    "sell": cmd_sell,
    "get-rate": cmd_get_rate,
    "help": cmd_help,
}


def run() -> None:
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
        if handler:
            try:
                handler(tokens)
            except usecases.UsecaseError as e:
                print(e)
        else:
            print(f"Неизвестная команда: {cmd}. Введите 'help'.")