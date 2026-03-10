import inspect
from typing import Any, Callable

from src.shared.logger import get_logger

logger = get_logger(__name__)

def command(name: str) -> Callable:
    """Декоратор для регистрации обработчика текстовой команды (начинается с /)."""
    def decorator(func: Callable) -> Callable:
        func.__command__ = name
        return func
    return decorator

def callback(prefix: str) -> Callable:
    """Декоратор для регистрации обработчика callback_query по префиксу date."""
    def decorator(func: Callable) -> Callable:
        func.__callback__ = prefix
        return func
    return decorator

def message() -> Callable:
    """Декоратор для регистрации обработчика обычных текстовых сообщений (стейт-машина)."""
    def decorator(func: Callable) -> Callable:
        func.__message__ = True
        return func
    return decorator

def document() -> Callable:
    """Декоратор для обработки документов."""
    def decorator(func: Callable) -> Callable:
        func.__document__ = True
        return func
    return decorator

class Router:
    """Реестр обработчиков и инжектор зависимостей для вызовов."""

    def __init__(self) -> None:
        self.commands: dict[str, Callable] = {}
        self.callbacks: dict[str, Callable] = {}
        self.message_handlers: list[Callable] = []
        self.document_handlers: list[Callable] = []

    def include_class(self, instance: Any) -> None:
        """Регистрирует методы переданного экземпляра в роутер."""
        for _name, method in inspect.getmembers(instance, predicate=inspect.ismethod):
            if hasattr(method, "__command__"):
                self.commands[method.__command__] = method
            elif hasattr(method, "__callback__"):
                self.callbacks[method.__callback__] = method
            elif hasattr(method, "__message__"):
                self.message_handlers.append(method)
            elif hasattr(method, "__document__"):
                self.document_handlers.append(method)

    async def execute_handler(self, handler: Callable, **kwargs: Any) -> Any:
        """Инжектит необходимые аргументы в обработчик по их именам и вызывает его."""
        sig = inspect.signature(handler)
        bound_args = {}
        for param_name in sig.parameters:
            if param_name in kwargs:
                bound_args[param_name] = kwargs[param_name]
            # В противном случае пропускаем аргумент. 
            # Либо можно выбросить ошибку если нет дефолтного значения:
            # elif param.default == inspect.Parameter.empty: logger.error...
        return await handler(**bound_args)
