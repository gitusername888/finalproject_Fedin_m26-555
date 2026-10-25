"""
Декоратор @log_action: трассировка доменных операций (BUY/SELL/REGISTER/LOGIN).

Декоратор НЕ глотает исключения — фиксирует их в лог и пробрасывает дальше.
Структура записи: timestamp, action, username, currency_code, amount,
rate/base (если применимо), result (OK/ERROR), error_type/error_message.
"""
import functools
import inspect
import logging
from datetime import datetime, timezone
from typing import Any, Callable

from valutatrade_hub.infra.settings import SettingsLoader


def _fmt(value: Any, spec: str = ".4f") -> str:
    try:
        return format(float(value), spec)
    except (TypeError, ValueError):
        return str(value)


def log_action(action: str, verbose: bool | None = None) -> Callable:
    """Декоратор логирования операций usecases.

    verbose=True добавляет контекст "было -> стало" для операций с кошельком.
    Если verbose не передан — берётся из конфигурации (log_verbose).
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Связываем фактические аргументы с именами параметров функции
            bound = inspect.signature(func).bind(*args, **kwargs)
            bound.apply_defaults()
            params = dict(bound.arguments)

            logger = logging.getLogger("valutatrade")
            use_verbose = verbose
            if use_verbose is None:
                use_verbose = bool(SettingsLoader().get("log_verbose", False))

            ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
            user_obj = params.get("user")
            username = getattr(user_obj, "username", None) or params.get("username") or "-"

            fields = [action, f"user='{username}'"]

            currency = params.get("currency_code")
            if currency:
                fields.append(f"currency='{str(currency).strip().upper()}'")

            amount = params.get("amount")
            if amount is not None:
                fields.append(f"amount={_fmt(amount)}")

            base = params.get("base_currency") or "USD"
            fields.append(f"base='{base}'")

            try:
                result = func(*args, **kwargs)
            except Exception as exc:
                fields.append(
                    f"result=ERROR error_type={type(exc).__name__} "
                    f"error_message='{exc}'"
                )
                logger.info(f"{ts} " + " ".join(fields))
                raise  # пробрасываем дальше — декоратор не глотает исключения

            rate = result.get("rate") if isinstance(result, dict) else None
            if rate is not None:
                fields.append(f"rate={_fmt(rate, '.2f')}")
            fields.append("result=OK")

            if use_verbose and isinstance(result, dict) and "was" in result:
                fields.append(
                    f"was={_fmt(result['was'])} became={_fmt(result.get('became', 0))}"
                )
            logger.info(f"{ts} " + " ".join(fields))
            return result

        return wrapper

    return decorator