"""Парсинг файлов .siq (SIGame)."""

import logging
import xml.etree.ElementTree as ET
import zipfile
from io import BytesIO
from urllib.parse import unquote

from src.application.parser.dto import (
    PackageDTO,
    QuestionDTO,
    RoundDTO,
    ThemeDTO,
)

logger = logging.getLogger("worker.parser")


class SiqParser:
    """Парсер .siq архивов"""

    def parse(self, file_path_or_bytes: str | bytes) -> PackageDTO:
        if isinstance(file_path_or_bytes, bytes):
            zf = zipfile.ZipFile(BytesIO(file_path_or_bytes))
        else:
            zf = zipfile.ZipFile(file_path_or_bytes)

        with zf:
            try:
                content = zf.read("content.xml")
            except KeyError as e:
                raise ValueError("Файл не является валидным .siq архивом") from e

            # Создаем список ВСЕХ файлов в архиве (только их имена, чтобы легко искать)
            # Например: ['Images/cat.jpg', 'Audio/sound.mp3']
            all_files_in_zip = zf.namelist()

            images_in_zip = [f for f in all_files_in_zip if f.lower().startswith("images/")]
            logger.info(f"📁 РЕАЛЬНЫЕ КАРТИНКИ В АРХИВЕ (первые 20): {images_in_zip[:20]}")

            # Передаем этот список в парсер XML
            return self._parse_xml(content, zf, all_files_in_zip)

    @staticmethod
    def _parse_xml(xml_bytes: bytes, zf: zipfile.ZipFile, all_files_in_zip: list[str]) -> PackageDTO:
        """Разбор content.xml."""

        tree = ET.fromstring(xml_bytes)

        # Обход namespaces
        for elem in tree.iter():
            if "}" in elem.tag:
                elem.tag = elem.tag.split("}", 1)[1]

        title = tree.attrib.get("name", "Unknown Package")

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

                            q_text = ""
                            media_type = None
                            media_bytes = None
                            media_filename = None

                            for element in question_node.iter():
                                tag_name = element.tag.lower()
                                if tag_name not in ["atom", "item"]:
                                    continue

                                if not element.text:
                                    continue

                                elem_type = element.attrib.get("type", "text").lower()
                                is_ref = element.attrib.get("isRef", "false").lower() == "true"
                                text_value = element.text.strip()

                                # Обработка текста
                                if elem_type == "text" and not is_ref:
                                    q_text += text_value + " "

                                # Обработка медиафайлов
                                elif elem_type in ["image", "video", "audio", "voice"]:
                                    if is_ref or text_value.startswith("@"):
                                        raw_filename = text_value[1:] if text_value.startswith("@") else text_value
                                        filename = unquote(raw_filename)

                                        if elem_type == "image":
                                            current_media_type = "photo"
                                            folder = "Images"
                                        elif elem_type == "video":
                                            current_media_type = "video"
                                            folder = "Video"
                                        else:
                                            current_media_type = "audio"
                                            folder = "Audio"

                                        # Берем ПЕРВЫЙ найденный медиафайл (если их в вопросе несколько)
                                        if media_bytes is None:
                                            # Ищем файл в архиве. Сначала точное совпадение:
                                            target_path = f"{folder}/{filename}"

                                            if target_path in all_files_in_zip:
                                                # Файл найден идеально
                                                media_bytes = zf.read(target_path)
                                                media_filename = filename
                                                media_type = current_media_type
                                            else:
                                                found_fuzzy = False
                                                # Приводим искомое имя к нижнему регистру для надежности
                                                safe_target = unquote(filename).lower()

                                                for real_file in all_files_in_zip:
                                                    # Раскодируем реальное имя из ZIP и тоже в нижний регистр
                                                    safe_real = unquote(real_file).lower()

                                                    # Ищем вхождение (даже частичное)
                                                    if safe_target in safe_real or safe_real.endswith(safe_target):
                                                        media_bytes = zf.read(real_file)
                                                        media_filename = real_file.split("/")[-1]
                                                        media_type = current_media_type
                                                        found_fuzzy = True
                                                        break

                                                if not found_fuzzy:
                                                    logger.warning(
                                                        f"Медиафайл '{target_path}' не найден в архиве ни по точному имени, ни через умный поиск!")
                            q_text = q_text.strip()
                            if not q_text and media_bytes:
                                q_text = "Внимание на экран:"
                            elif not q_text:
                                q_text = "[Пустой вопрос]"

                            answer_text = ""
                            right_node = question_node.find("right")
                            if right_node is not None:
                                ans_elem = right_node.find("answer")
                                if ans_elem is not None and ans_elem.text:
                                    answer_text = ans_elem.text.strip()

                            theme_dto.questions.append(
                                QuestionDTO(
                                    text=q_text,
                                    answer=answer_text,
                                    value=price,
                                    media_type=media_type,
                                    media_bytes=media_bytes,
                                    media_filename=media_filename
                                )
                            )

                    round_dto.themes.append(theme_dto)

            package_dto.rounds.append(round_dto)

        # Подсчет успешно извлеченных файлов перед возвратом DTO
        files_found = sum(
            1 for r in package_dto.rounds for t in r.themes for q in t.questions if q.media_bytes
        )
        logger.info(f"Парсер извлек байты для {files_found} медиафайлов из пакета '{title}'.")

        return package_dto