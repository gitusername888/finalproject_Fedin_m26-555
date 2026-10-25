"""
Singleton SettingsLoader: единая точка конфигурации проекта.

Выбран способ через __new__ (а не метакласс) — он проще и читаемее:
один переопределённый метод, без дополнительного уровня абстракции,
а для одного-двух синглтонов этого более чем достаточно.
"""
import json
import tomllib
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[2]  # корень проекта

# Ключи конфигурации по умолчанию (минимальный набор из ТЗ)
DEFAULTS: dict = {
    "data_dir": "data",                    # путь к JSON-хранилищу
    "rates_ttl_seconds": 300,              # политика свежести курсов (5 минут)
    "default_base_currency": "USD",        # базовая валюта по умолчанию
    "log_file": "logs/actions.log",        # путь к файлу логов
    "log_level": "INFO",                   # уровень логирования (DEBUG для отладки)
    "log_format": "text",                  # формат логов: text | json
    "log_max_bytes": 5 * 1024 * 1024,      # ротация: макс. размер файла
    "log_backup_count": 3,                 # ротация: число резервных копий
    "log_verbose": False,                  # verbose-режим декоратора @log_action
}


class SettingsLoader:
    """Синглтон: в приложении существует ровно один экземпляр."""

    _instance: "SettingsLoader | None" = None

    def __new__(cls) -> "SettingsLoader":
        if cls._instance is None:
            instance = super().__new__(cls)
            instance._config: dict = dict(DEFAULTS)
            instance._load_external_config()
            cls._instance = instance
        return cls._instance

    # --- загрузка внешней конфигурации ---
    def _load_external_config(self) -> None:
        # Приоритет 1: секция [tool.valutatrade] в pyproject.toml
        pyproject = BASE_DIR / "pyproject.toml"
        if pyproject.exists():
            try:
                data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
                section = data.get("tool", {}).get("valutatrade", {})
                if isinstance(section, dict):
                    self._config.update(section)
                return
            except (tomllib.TOMLDecodeError, OSError):
                pass
        # Приоритет 2: config.json в корне проекта
        config_json = BASE_DIR / "config.json"
        if config_json.exists():
            try:
                data = json.loads(config_json.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    self._config.update(data)
            except (json.JSONDecodeError, OSError):
                pass

    # --- публичный интерфейс ---
    def get(self, key: str, default: Any = None) -> Any:
        return self._config.get(key, default)

    def reload(self) -> None:
        """Перезагрузка конфигурации из внешних источников."""
        self._config = dict(DEFAULTS)
        self._load_external_config()

    @property
    def data_dir(self) -> Path:
        path = Path(str(self._config["data_dir"]))
        return path if path.is_absolute() else BASE_DIR / path

    def log_file_path(self) -> Path:
        path = Path(str(self._config["log_file"]))
        return path if path.is_absolute() else BASE_DIR / path