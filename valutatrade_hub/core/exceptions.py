"""
Пользовательские исключения проекта ValutaTrade Hub.

Каждое исключение несёт готовое пользовательское сообщение (str(exc)),
которое CLI печатает как есть.
"""


class ValutaTradeError(Exception):
    """Базовый класс всех ошибок бизнес-логики проекта."""


class InsufficientFundsError(ValutaTradeError):
    """Недостаточно средств на кошельке.

    Возникает в Wallet.withdraw() и в usecases.sell_currency().
    Сообщение: "Недостаточно средств: доступно {available} {code}, требуется {required} {code}"
    """

    def __init__(self, available: float, required: float, code: str):
        self.available = available
        self.required = required
        self.code = code
        super().__init__(
            f"Недостаточно средств: доступно {available:.4f} {code}, "
            f"требуется {required:.4f} {code}"
        )


class CurrencyNotFoundError(ValutaTradeError):
    """Неизвестный код валюты.

    Возникает в currencies.get_currency() и при валидации входа get-rate.
    Сообщение: "Неизвестная валюта '{code}'"
    """

    def __init__(self, code: str):
        self.code = code
        super().__init__(f"Неизвестная валюта '{code}'")


class ApiRequestError(ValutaTradeError):
    """Сбой при обращении к внешнему API (слою получения курсов).

    Сообщение: "Ошибка при обращении к внешнему API: {reason}"
    """

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(f"Ошибка при обращении к внешнему API: {reason}")
