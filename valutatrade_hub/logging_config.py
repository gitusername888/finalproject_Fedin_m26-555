"""
Настройка логов проекта.

Формат зафиксирован: человекочитаемый текст (log_format=text),
строка лога собирается декоратором @log_action в едином виде:
    INFO 2025-10-09T12:05:22+00:00 BUY user='alice' currency='BTC' ... result=OK

Ротация: RotatingFileHandler (по размеру файла), параметры — в конфиге.
Уровень по умолчанию: INFO (для отладки выставить DEBUG в конфиге).
"""
import logging
import logging.handlers

from valutatrade_hub.infra.settings import SettingsLoader

_logger_name = "valutatrade"


def setup_logging() -> logging.Logger:
    """Идемпотентная инициализация: повторный вызов не дублирует хендлеры."""
    logger = logging.getLogger(_logger_name)
    if getattr(logger, "_valutatrade_configured", False):
        return logger

    settings = SettingsLoader()
    log_path = settings.log_file_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)

    handler = logging.handlers.RotatingFileHandler(
        log_path,
        maxBytes=int(settings.get("log_max_bytes", 5 * 1024 * 1024)),
        backupCount=int(settings.get("log_backup_count", 3)),
        encoding="utf-8",
    )
    # timestamp попадает в сообщение декоратора (ISO), формат — только уровень + текст
    handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))

    logger.setLevel(str(settings.get("log_level", "INFO")).upper())
    logger.addHandler(handler)
    logger.propagate = False
    logger._valutatrade_configured = True  # type: ignore[attr-defined]
    return logger