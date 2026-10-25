"""Клиенты внешних API: унифицированный интерфейс fetch_rates().

Оба клиента приводят ответы разных API к единому формату:
    {"BTC_USD": 59337.21, "EUR_USD": 1.0786, ...}
то есть "код_валюты_USD" -> сколько долларов стоит 1 единица валюты.
Любые проблемы (сеть, HTTP-статус, формат ответа) -> ApiRequestError.
"""

import logging
from abc import ABC, abstractmethod

import requests

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.parser_service.config import ParserConfig

logger = logging.getLogger("parser_service.api_clients")


class BaseApiClient(ABC):
    """Общий интерфейс для всех источников курсов."""

    source_name: str = "base"  # имя источника для метаданных и логов

    @abstractmethod
    def fetch_rates(self) -> dict:
        """Возвращает {"<CODE>_USD": rate, ...} или бросает ApiRequestError."""
        raise NotImplementedError

    # --- общий вспомогательный метод для GET-запросов ---
    def _get_json(self, url: str, params: dict | None = None) -> dict:
        try:
            response = requests.get(
                url,
                params=params,
                timeout=self._config.REQUEST_TIMEOUT,
            )
        except requests.exceptions.Timeout:
            raise ApiRequestError(
                f"источник {self.source_name} не ответил за "
                f"{self._config.REQUEST_TIMEOUT} секунд (таймаут)"
            )
        except requests.exceptions.RequestException as exc:
            raise ApiRequestError(f"сетевая ошибка при обращении к {self.source_name}: {exc}")

        if response.status_code != 200:
            raise ApiRequestError(
                f"{self.source_name} вернул HTTP {response.status_code}: {response.text[:200]}"
            )

        try:
            return response.json()
        except ValueError as exc:
            raise ApiRequestError(f"{self.source_name} вернул некорректный JSON: {exc}")

    @staticmethod
    def _check_rate(value, source: str) -> float:
        """Валидация типа данных: курс должен быть конечным числом > 0."""
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ApiRequestError(f"{source} вернул нечисловое значение курса: {value!r}")
        rate = float(value)
        if rate != rate or rate <= 0:  # NaN и нулевые/отрицательные курсы — мусор
            raise ApiRequestError(f"{source} вернул некорректный курс: {rate}")
        return rate


class CoinGeckoClient(BaseApiClient):
    """Курсы криптовалют: https://api.coingecko.com/api/v3/simple/price."""

    source_name = "CoinGecko"

    def __init__(self, config: ParserConfig | None = None):
        self._config = config or ParserConfig()

    def fetch_rates(self) -> dict:
        # ids — через CRYPTO_ID_MAP: CoinGecko работает с ID, а не с тикерами
        ids = ",".join(
            self._config.CRYPTO_ID_MAP[code] for code in self._config.CRYPTO_CURRENCIES
        )
        params = {
            "ids": ids,
            "vs_currencies": self._config.BASE_CURRENCY.lower(),  # "usd"
        }

        logger.info("Запрос к CoinGecko: ids=%s", ids)
        data = self._get_json(self._config.COINGECKO_URL, params=params)

        # Ответ: {"bitcoin": {"usd": 59337.21}, ...}
        rates = {}
        id_by_code = {v: k for k, v in self._config.CRYPTO_ID_MAP.items()}
        for coin_id, currencies in data.items():
            code = id_by_code.get(coin_id)
            if code is None:
                logger.warning("CoinGecko вернул неизвестный id: %s — пропущен", coin_id)
                continue
            value = currencies.get(self._config.BASE_CURRENCY.lower())
            if value is None:
                logger.warning("CoinGecko не вернул курс для %s — пропущено", coin_id)
                continue
            rates[f"{code}_{self._config.BASE_CURRENCY}"] = self._check_rate(value, "CoinGecko")

        logger.info("CoinGecko: получено курсов: %d", len(rates))
        return rates


class ExchangeRateApiClient(BaseApiClient):
    """Курсы фиатных валют: https://v6.exchangerate-api.com/v6/<KEY>/latest/USD."""

    source_name = "ExchangeRate-API"

    def __init__(self, config: ParserConfig | None = None):
        self._config = config or ParserConfig()

    def fetch_rates(self) -> dict:
        api_key = self._config.get_api_key()  # лениво: свежее значение окружения
        if not api_key:
            raise ApiRequestError(
                "API-ключ ExchangeRate-API не задан. "
                "Установите переменную окружения EXCHANGERATE_API_KEY"
            )

        base = self._config.BASE_CURRENCY
        url = f"{self._config.EXCHANGERATE_API_URL}/{api_key}/latest/{base}"

        logger.info("Запрос к ExchangeRate-API: base=%s", base)
        data = self._get_json(url)

        # Бизнес-ошибки API: неверный ключ (101), лимит (104) и т.п.
        result = data.get("result")
        if result != "success":
            error_type = data.get("error-type", "неизвестная ошибка")
            raise ApiRequestError(f"ExchangeRate-API: result={result!r}, error-type={error_type!r}")

        # Ответ: {"result": "success", "base_code": "USD",
        #         "rates": {"EUR": 0.927, "GBP": 0.809, "RUB": 98.45, ...}}
        rates = {}
        for code in self._config.FIAT_CURRENCIES:
            value = data.get("rates", {}).get(code)
            if value is None:
                logger.warning("ExchangeRate-API не вернул курс для %s — пропущено", code)
                continue
            # API даёт "сколько единиц валюты за 1 USD" (98.45 RUB/USD),
            # а наш стандартный формат — "USD за 1 единицу" (RUB_USD = 0.01016).
            usd_per_unit = 1.0 / self._check_rate(value, "ExchangeRate-API")
            rates[f"{code}_{base}"] = usd_per_unit

        logger.info("ExchangeRate-API: получено курсов: %d", len(rates))
        return rates