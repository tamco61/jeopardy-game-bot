from dataclasses import dataclass, field


@dataclass
class QuestionDTO:
    text: str
    answer: str
    value: int
    question_type: str = "normal"


@dataclass
class ThemeDTO:
    name: str
    questions: list[QuestionDTO] = field(default_factory=list)


@dataclass
class RoundDTO:
    name: str
    is_final: bool = False
    themes: list[ThemeDTO] = field(default_factory=list)


@dataclass
class PackageDTO:
    title: str
    author: str = ""
    rounds: list[RoundDTO] = field(default_factory=list)

