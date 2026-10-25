"""
Singleton DatabaseManager: абстракция над JSON-хранилищем.

Тоже реализован через __new__ (см. комментарий в settings.py):
простой и читаемый способ, гарантирующий один экземпляр на процесс.
"""
import json
import tempfile
import threading
from pathlib import Path
from typing import Any, Callable

from valutatrade_hub.infra.settings import SettingsLoader


class DatabaseManager:
    """Единая точка доступа к JSON-файлам data/*.json.

    Все операции чтение -> модификация -> запись должны идти через
    один экземпляр: это исключает рассинхронизацию записей из разных
    частей кода. Запись атомарная (через временный файл + replace).
    """

    _instance: "DatabaseManager | None" = None

    def __new__(cls) -> "DatabaseManager":
        if cls._instance is None:
            instance = super().__new__(cls)
            instance._lock = threading.Lock()
            settings = SettingsLoader()
            data_dir = settings.data_dir
            data_dir.mkdir(parents=True, exist_ok=True)
            instance._paths: dict = {
                "users": data_dir / "users.json",
                "portfolios": data_dir / "portfolios.json",
                "rates": data_dir / "rates.json",
            }
            cls._instance = instance
        return cls._instance

    # --- чтение ---
    def load(self, name: str, default_factory: Callable[[], Any]) -> Any:
        """Безопасное чтение: повреждённый/отсутствующий файл -> default."""
        path = self._paths.get(name)
        if path is None:
            raise KeyError(f"Неизвестное хранилище: {name}")
        with self._lock:
            if not path.exists():
                return default_factory()
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return default_factory()
            return data if data is not None else default_factory()

    # --- запись ---
    def save(self, name: str, data: Any) -> None:
        """Атомарная запись: сначала временный файл, затем replace."""
        path = self._paths.get(name)
        if path is None:
            raise KeyError(f"Неизвестное хранилище: {name}")
        with self._lock:
            tmp_fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
            try:
                with open(tmp_fd, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                Path(tmp_name).replace(path)
            finally:
                if Path(tmp_name).exists():
                    Path(tmp_name).unlink(missing_ok=True)

    def path_for(self, name: str) -> Path:
        return self._paths[name]
