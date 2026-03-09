from pydantic import BaseModel, Field


class QuestionDTO(BaseModel):
    text: str
    answer: str
    value: int
    question_type: str = "normal"


class ThemeDTO(BaseModel):
    name: str
    questions: list[QuestionDTO] = Field(default_factory=list)


class RoundDTO(BaseModel):
    name: str
    is_final: bool = False
    themes: list[ThemeDTO] = Field(default_factory=list)


class PackageDTO(BaseModel):
    title: str
    author: str = ""
    rounds: list[RoundDTO] = Field(default_factory=list)

