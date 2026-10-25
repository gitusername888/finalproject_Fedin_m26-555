import hashlib
import os
import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any


class User:
    def __init__(
        self,
        user_id: int,
        username: str,
        password: str,
        registration_date: Optional[str] = None,
    ):
        self._user_id = user_id
        self.username = username  # сеттер проверит, что имя не пустое

        if registration_date is None:
            registration_date = datetime.now(timezone.utc).isoformat()
        self._registration_date = registration_date

        # Хешируем пароль с солью (change_password сам валидирует длину)
        self.change_password(password)

    # --- user_id (только чтение) ---
    @property
    def user_id(self) -> int:
        return self._user_id

    # --- username (чтение + запись с валидацией) ---
    @property
    def username(self) -> str:
        return self._username

    @username.setter
    def username(self, value: str) -> None:
        if not value or not value.strip():
            raise ValueError("Имя пользователя не может быть пустым.")
        self._username = value.strip()

    # --- hashed_password (внутреннее хранение) ---
    @property
    def _hashed_password(self) -> str:
        return self.__hashed_password

    @_hashed_password.setter
    def _hashed_password(self, value: str) -> None:
        self.__hashed_password = value

    # --- salt (внутреннее хранение) ---
    @property
    def _salt(self) -> str:
        return self.__salt

    @_salt.setter
    def _salt(self, value: str) -> None:
        self.__salt = value

    # --- registration_date (только чтение) ---
    @property
    def registration_date(self) -> str:
        return self._registration_date

    @staticmethod
    def _hash_password(password: str, salt: str) -> str:
        """Односторонний псевдо-хеш: sha256(password + salt)."""
        data = (password + salt).encode("utf-8")
        return hashlib.sha256(data).hexdigest()

    @staticmethod
    def generate_salt() -> str:
        """Генерирует случайную соль."""
        return os.urandom(16).hex()

    def change_password(self, new_password: str) -> None:
        if len(new_password) < 4:
            raise ValueError("Пароль должен быть не короче 4 символов.")
        new_salt = self.generate_salt()
        new_hash = self._hash_password(new_password, new_salt)
        self._salt = new_salt
        self._hashed_password = new_hash

    def check_password(self, raw_password: str) -> bool:
        """Сверяет введённый пароль с сохранённым хешем (для команды login)."""
        return self._hash_password(raw_password, self._salt) == self._hashed_password

    def get_user_info(self) -> Dict[str, Any]:
        """Публичная информация о пользователе. Пароль не возвращается."""
        return {
            "user_id": self.user_id,
            "username": self.username,
            "hashed_password": self._hashed_password,
            "salt": self._salt,
            "registration_date": self.registration_date,
        }

    def to_dict(self) -> Dict[str, Any]:
        """Сериализация для сохранения в users.json."""
        return self.get_user_info()

    @classmethod
    def from_record(cls, record: dict) -> "User":
        """
        Восстановление пользователя из JSON-записи users.json.
        Пароль не хешируется повторно: берутся сохранённые salt и hash.
        """
        user = cls.__new__(cls)
        user._user_id = record["user_id"]
        user._username = record["username"]
        user._registration_date = record.get(
            "registration_date", datetime.now(timezone.utc).isoformat()
        )
        user._salt = record["salt"]
        user._hashed_password = record["hashed_password"]
        return user


class Wallet:
    """Кошелёк пользователя для одной конкретной валюты (USD, BTC и т.д.)."""

    def __init__(self, currency_code: str, balance: float = 0.0):
        self.currency_code = currency_code
        self.balance = balance  # инициализация через сеттер — сработает валидация

    # --- currency_code ---
    @property
    def currency_code(self) -> str:
        return self._currency_code

    @currency_code.setter
    def currency_code(self, value: str) -> None:
        if not value or not value.strip():
            raise ValueError("Код валюты не может быть пустым.")
        self._currency_code = value.strip().upper()

    # --- balance: геттер + сеттер с проверками ---
    @property
    def balance(self) -> float:
        return self._balance

    @balance.setter
    def balance(self, value) -> None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("Баланс должен быть числом (int или float).")
        if value < 0:
            raise ValueError("Баланс не может быть отрицательным.")
        self._balance = float(value)

    @staticmethod
    def _validate_amount(amount, operation: str) -> float:
        if isinstance(amount, bool) or not isinstance(amount, (int, float)):
            raise TypeError(
                f"Сумма операции '{operation}' должна быть числом (int или float)."
            )
        if amount <= 0:
            raise ValueError(f"Сумма операции '{operation}' должна быть положительной.")
        return float(amount)

    def deposit(self, amount: float) -> float:
        amount = self._validate_amount(amount, "deposit")
        self._balance += amount
        return self._balance

    def withdraw(self, amount: float) -> float:
        amount = self._validate_amount(amount, "withdraw")
        if amount > self._balance:
            raise ValueError(
                f"Недостаточно средств: баланс {self._balance:.2f} {self.currency_code}, "
                f"запрошено к снятию {amount:.2f} {self.currency_code}."
            )
        self._balance -= amount
        return self._balance

    def get_balance_info(self) -> str:
        return f"Валюта: {self.currency_code}, баланс: {self._balance:.2f}"

    def to_dict(self) -> dict:
        return {
            "currency_code": self.currency_code,
            "balance": self._balance,
        }


class Portfolio:
    """Управление всеми кошельками одного пользователя."""

    exchange_rates = {
        "USD": 1.0,
        "EUR": 0.92,
        "RUB": 92.0,
        "BTC": 0.0000152,
        "ETH": 0.00031,
    }

    def __init__(self, user: User, wallets: Optional[Dict[str, Wallet]] = None):
        self._user = user
        self._wallets: Dict[str, Wallet] = dict(wallets) if wallets else {}

    @property
    def user(self) -> User:
        return self._user

    @property
    def wallets(self) -> Dict[str, Wallet]:
        return dict(self._wallets)

    @property
    def user_id(self) -> int:
        return self._user.user_id

    @staticmethod
    def _validate_currency_code(currency_code: str) -> str:
        if not currency_code or not currency_code.strip():
            raise ValueError("Код валюты не может быть пустым.")
        return currency_code.strip().upper()

    def add_currency(self, currency_code: str) -> Wallet:
        code = self._validate_currency_code(currency_code)
        if code in self._wallets:
            raise ValueError(
                f"Кошелёк в валюте {code} уже есть в портфеле пользователя "
                f"{self._user.username}."
            )
        wallet = Wallet(code)
        self._wallets[code] = wallet
        return wallet

    def get_wallet(self, currency_code: str) -> Wallet:
        code = self._validate_currency_code(currency_code)
        if code not in self._wallets:
            raise KeyError(f"Кошелька в валюте {code} нет в портфеле.")
        return self._wallets[code]

    def get_total_value(self, base_currency: str = "USD") -> float:
        base = self._validate_currency_code(base_currency)
        if base not in self.exchange_rates:
            raise ValueError(f"Курс для базовой валюты {base} неизвестен.")
        total_usd = 0.0
        for wallet in self._wallets.values():
            rate = self.exchange_rates.get(wallet.currency_code)
            if rate is None:
                raise ValueError(
                    f"Нет курса для валюты {wallet.currency_code} — "
                    f"не могу посчитать стоимость."
                )
            total_usd += wallet.balance / rate
        return total_usd * self.exchange_rates[base]

    def buy_currency(self, currency_code: str, amount: float) -> None:
        code = self._validate_currency_code(currency_code)
        if code not in self.exchange_rates:
            raise ValueError(f"Нет курса для валюты {code} — покупка невозможна.")
        usd_wallet = self.get_wallet("USD")
        cost_in_usd = amount / self.exchange_rates[code]
        usd_wallet.withdraw(cost_in_usd)
        # Кошелёк покупаемой валюты создаётся автоматически при первой покупке
        wallet = self._wallets.get(code)
        if wallet is None:
            wallet = self.add_currency(code)
        wallet.deposit(amount)

    def sell_currency(self, currency_code: str, amount: float) -> None:
        code = self._validate_currency_code(currency_code)
        if code not in self.exchange_rates:
            raise ValueError(f"Нет курса для валюты {code} — продажа невозможна.")
        wallet = self.get_wallet(code)
        proceeds_in_usd = amount / self.exchange_rates[code]
        wallet.withdraw(amount)
        self.get_wallet("USD").deposit(proceeds_in_usd)

    def to_record(self) -> dict:
        """Формат для portfolios.json: user_id + словарь кошельков с балансами."""
        return {
            "user_id": self.user_id,
            "wallets": {
                code: {"balance": wallet.balance}
                for code, wallet in self._wallets.items()
            },
        }

    def to_dict(self) -> dict:
        return self.to_record()

    @classmethod
    def from_record(cls, user: User, data: dict) -> "Portfolio":
        wallets = {
            code: Wallet(code, balance=item["balance"])
            for code, item in data.get("wallets", {}).items()
        }
        return cls(user=user, wallets=wallets)

    @classmethod
    def from_dict(cls, user: User, data: dict) -> "Portfolio":
        return cls.from_record(user, data)
