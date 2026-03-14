from typing import ClassVar

from pydantic import BaseModel


class CallbackBase(BaseModel):
    """Базовый класс для всех типизированных колбеков клавиатуры"""
    prefix: ClassVar[str]
    sep: ClassVar[str] = ":"

    def pack(self) -> str:
        """Собирает строку для кнопки"""
        # Достаем значения всех полей в порядке их объявления, пропуская ClassVar
        values = [str(getattr(self, field)) for field in self.model_fields]
        return self.sep.join([self.prefix, *values])

    @classmethod
    def parse(cls, data: str) -> "CallbackBase":
        """Разбирает строку и инициализирует объект Pydantic"""
        parts = data.split(cls.sep)
        if parts[0] != cls.prefix:
            raise ValueError(f"Invalid prefix: expected {cls.prefix}, got {parts[0]}")
        
        # Собираем аргументы по именам полей 
        field_names = list(cls.model_fields.keys())
        # Нужно учитывать, что значений может быть больше (напр. если строка 'prefix:id' и т.д.)
        kwargs = dict(zip(field_names, parts[1:], strict=False))
        return cls(**kwargs)


class SelectPackCallback(CallbackBase):
    prefix: ClassVar[str] = "sp"
    room_id: str
    pack_id: int


class SelectQuestionCallback(CallbackBase):
    prefix: ClassVar[str] = "sq"
    room_id: str
    question_id: int


class PressButtonCallback(CallbackBase):
    prefix: ClassVar[str] = "btn"
    chat_id: int


class VerdictCallback(CallbackBase):
    prefix: ClassVar[str] = "vd"
    room_id: str
    verdict: str
    target_player_id: str


class SkipRoundCallback(CallbackBase):
    prefix: ClassVar[str] = "sr"
    room_id: str


class FinalStartStakesCallback(CallbackBase):
    prefix: ClassVar[str] = "fss"
    room_id: str


class FinalCloseStakesCallback(CallbackBase):
    prefix: ClassVar[str] = "fcs"
    room_id: str


class FinalRevealCallback(CallbackBase):
    prefix: ClassVar[str] = "frv"
    room_id: str


class LobbyReadyCallback(CallbackBase):
    prefix: ClassVar[str] = "lr"


class LobbyNotReadyCallback(CallbackBase):
    prefix: ClassVar[str] = "lnr"


class LobbyLeaveCallback(CallbackBase):
    prefix: ClassVar[str] = "ll"


class StartGameCallback(CallbackBase):
    prefix: ClassVar[str] = "sg"


class StakeCallback(CallbackBase):
    prefix: ClassVar[str] = "stk"
    room_id: str
    amount: int
