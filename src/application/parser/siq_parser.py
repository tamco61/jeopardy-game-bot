"""Парсинг файлов .siq (SIGame)."""

import xml.etree.ElementTree as ET
import zipfile
from io import BytesIO

from src.application.parser.dto import (
    PackageDTO,
    QuestionDTO,
    RoundDTO,
    ThemeDTO,
)


class SiqParser:
    """Парсер .siq архивов"""

    def parse(self, file_path_or_bytes: str | bytes) -> PackageDTO:
        """Распарсить zip-архив .siq и вернуть DTO пакета."""

        # Если передали bytes, распаковываем из памяти, иначе читаем файл
        if isinstance(file_path_or_bytes, bytes):
            zf = zipfile.ZipFile(BytesIO(file_path_or_bytes))
        else:
            zf = zipfile.ZipFile(file_path_or_bytes)

        with zf:
            try:
                content = zf.read("content.xml")
            except KeyError as e:
                raise ValueError(
                    "Файл не является валидным .siq архивом (отсутствует content.xml)"
                ) from e

        return self._parse_xml(content)

    @staticmethod
    def _parse_xml(xml_bytes: bytes) -> PackageDTO:
        """Разбор content.xml."""
        # Для борьбы с namespace'ами XML в SIGame:
        # Обычно корень <package xmlns="http://vladimirkhil.com/ygpackage3.0.xsd" ...>
        # Чтобы не мучиться

        tree = ET.fromstring(xml_bytes)

        # Обход namespaces (если они есть)
        for elem in tree.iter():
            if "}" in elem.tag:
                elem.tag = elem.tag.split("}", 1)[1]

        title = tree.attrib.get("name", "Unknown Package")

        # Получаем автора
        author = ""
        info_node = tree.find("info")
        if info_node is not None:
            authors_node = info_node.find("authors")
            if authors_node is not None:
                author_elem = authors_node.find("author")
                if author_elem is not None and author_elem.text:
                    author = author_elem.text.strip()

        package_dto = PackageDTO(title=title, author=author)

        rounds_node = tree.find("rounds")
        if rounds_node is None:
            return package_dto

        for round_node in rounds_node.findall("round"):
            round_name = round_node.attrib.get("name", "Round")
            round_type = round_node.attrib.get("type", "standard")
            is_final = round_type.lower() == "final"

            round_dto = RoundDTO(name=round_name, is_final=is_final)

            themes_node = round_node.find("themes")
            if themes_node is not None:
                for theme_node in themes_node.findall("theme"):
                    theme_name = theme_node.attrib.get("name", "Theme")
                    theme_dto = ThemeDTO(name=theme_name)

                    questions_node = theme_node.find("questions")
                    if questions_node is not None:
                        for question_node in questions_node.findall("question"):
                            price = int(question_node.attrib.get("price", "0"))

                            # Извлекаем текст вопроса
                            q_text = ""
                            scenario_node = question_node.find("scenario")
                            if scenario_node is not None:
                                for atom in scenario_node.findall("atom"):
                                    atom_type = atom.attrib.get("type", "text")
                                    # Для MVP берем только текст, игнорируем медиа @audio, @image
                                    if atom.text and atom_type == "text":
                                        q_text += atom.text + " "

                            q_text = q_text.strip()
                            if not q_text:
                                q_text = "[Вопрос содержит только медиафайл]"

                            # Извлекаем ответ
                            answer_text = ""
                            right_node = question_node.find("right")
                            if right_node is not None:
                                ans_elem = right_node.find("answer")
                                if ans_elem is not None and ans_elem.text:
                                    answer_text = ans_elem.text.strip()

                            theme_dto.questions.append(
                                QuestionDTO(
                                    text=q_text, answer=answer_text, value=price
                                )
                            )

                    round_dto.themes.append(theme_dto)

            package_dto.rounds.append(round_dto)

        return package_dto
