"""
Иерархия валют: абстрактный базовый класс Currency и наследники
FiatCurrency / CryptoCurrency + реестр с фабрикой get_currency().
"""
from abc import ABC, abstractmethod
from typing import Dict, List

from valutatrade_hub.core.exceptions import CurrencyNotFoundError


class Currency(ABC):
    """Базовый класс валюты.

    Инварианты:
      - code: верхний регистр, 2-5 символов, без пробелов;
      - name: непустая строка.
    """

    def __init__(self, code: str, name: str):
        self.code = code
        self.name = name

    # --- code ---
    @property
    def code(self) -> str:
        return self._code

    @code.setter
    def code(self, value: str) -> None:
        v = (value or "").strip().upper()
        if not v or not (2 <= len(v) <= 5) or " " in v:
            raise ValueError(
                "Код валюты должен быть строкой из 2-5 символов без пробелов (верхний регистр)."
            )
        self._code = v

    # --- name ---
    @property
    def name(self) -> str:
        return self._name

    @name.setter
    def name(self, value: str) -> None:
        if not value or not value.strip():
            raise ValueError("Название валюты не может быть пустым.")
        self._name = value.strip()

    @abstractmethod
    def get_display_info(self) -> str:
        """Строковое представление для UI/логов."""

    def __repr__(self) -> str:  # noqa: D105
        return f"<{type(self).__name__} {self.code}>"


class FiatCurrency(Currency):
    """Фиатная валюта: добавляет страну/зону эмиссии."""

    def __init__(self, code: str, name: str, issuing_country: str):
        super().__init__(code, name)
        if not issuing_country or not issuing_country.strip():
            raise ValueError("Страна эмиссии не может быть пустой.")
        self.issuing_country = issuing_country.strip()

    def get_display_info(self) -> str:
        return f"[FIAT] {self.code} — {self.name} (Issuing: {self.issuing_country})"


class CryptoCurrency(Currency):
    """Криптовалюта: алгоритм майнинга/консенсуса и капитализация."""

    def __init__(self, code: str, name: str, algorithm: str, market_cap: float):
        super().__init__(code, name)
        if not algorithm or not algorithm.strip():
            raise ValueError("Алгоритм не может быть пустым.")
        if isinstance(market_cap, bool) or not isinstance(market_cap, (int, float)) or market_cap < 0:
            raise ValueError("Капитализация должна быть неотрицательным числом.")
        self.algorithm = algorithm.strip()
        self.market_cap = float(market_cap)

    def get_display_info(self) -> str:
        # Формат капитализации: 1.12e+12 -> 1.12e12 (как в ТЗ)
        mcap = f"{self.market_cap:.2e}".replace("e+", "e")
        return f"[CRYPTO] {self.code} — {self.name} (Algo: {self.algorithm}, MCAP: {mcap})"


class CurrencyRegistry:
    """Реестр поддерживаемых валют + фабрика get_currency()."""

    _currencies: Dict[str, Currency] = {}

    @classmethod
    def register(cls, currency: Currency) -> None:
        cls._currencies[currency.code] = currency

    @classmethod
    def get(cls, code: str) -> Currency:
        normalized = (code or "").strip().upper()
        if normalized not in cls._currencies:
            raise CurrencyNotFoundError(code)
        return cls._currencies[normalized]

    @classmethod
    def supported_codes(cls) -> List[str]:
        return sorted(cls._currencies)

    @classmethod
    def all_currencies(cls) -> List[Currency]:
        return list(cls._currencies.values())


def get_currency(code: str) -> Currency:
    """Фабричный метод: возвращает валюту по коду или бросает CurrencyNotFoundError."""
    return CurrencyRegistry.get(code)


# Встроенный реестр валют проекта
for _c in (
    FiatCurrency("USD", "US Dollar", "United States"),
    FiatCurrency("EUR", "Euro", "Eurozone"),
    FiatCurrency("RUB", "Russian Ruble", "Russia"),
    CryptoCurrency("BTC", "Bitcoin", "SHA-256", 1.12e12),
    CryptoCurrency("ETH", "Ethereum", "Ethash", 3.7e11),
):
    CurrencyRegistry.register(_c)
