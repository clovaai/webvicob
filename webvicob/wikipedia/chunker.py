"""
WEBVICOB
Copyright 2022-present NAVER Corp.
Apache-2.0
"""
import re

from bs4 import BeautifulSoup


class WikiHtmlChunker:
    SECTION_START_PATTERN = '<section data-mw-section-id="[\-0-9]+" id="[\-a-zA-Z0-9]+">'
    SECTION_END_PATTERN = "</section>"

    def __init__(
        self,
        min_section_tokens: int = 100,
        min_section_chars: int = None,
        append_title: bool = True,
        max_section_depth: int = 0,
    ):
        # wikipedia chunk options
        self.min_section_tokens = min_section_tokens
        self.min_section_chars = min_section_chars
        self.append_title = append_title
        self.max_section_depth = max_section_depth

    def __call__(self, html: str):
        chunks = []

        soup = BeautifulSoup(html, "html.parser")
        sections = soup.find_all("section")
        sections = self.extract_sections(sections)

        section_indexes = self.extract_section_indexes(html, sections)
        if len(section_indexes) < 1 or len(section_indexes[0]) < 1:
            return chunks

        html_front = html[: section_indexes[0][0]]
        if self.append_title:
            title_tag = self.extract_title_tag(html=html)
            html_front += title_tag

        html_back = html[section_indexes[-1][1] :]
        chunks = self.merge_into_chunks(sections, html_front, html_back)
        return chunks

    def extract_title_tag(self, html: str):
        title_tag = ""

        soup = BeautifulSoup(html, "html.parser")
        title = soup.find_all("title")
        if len(title) > 0:
            title = title[0].text
            title_tag = '<h1 id="firstHeading" class="firstHeading mw-first-heading">' + title + "</h1>"

        return title_tag

    def extract_children_tag_names(self, html: str, parent_name: str = None):
        soup = BeautifulSoup(html, "html.parser")
        if parent_name is None:
            parent_name = soup.name

        children = soup.findChildren()
        tag_names = []
        for child in children:
            if child.parent.name != parent_name:
                continue
            tag_names.append(child.name)
        return tag_names

    def extract_sections(self, sections, cur_depth=0):
        outputs = []
        for section in sections:
            _sections = section.find_all("section")
            if len(_sections) < 1 or cur_depth >= self.max_section_depth:
                outputs += [section]
            else:
                outputs += self.extract_sections(_sections, cur_depth + 1)
        return outputs

    def extract_section_indexes(self, html, sections):
        section_indexes = []
        for section in sections:
            search_res = re.search(self.SECTION_START_PATTERN, str(section))
            if search_res is None:
                continue

            section_start_tag = search_res.group()
            search_res = re.search(section_start_tag, html)
            if search_res is not None:
                begin_idx = search_res.start()
                search_res = re.search(self.SECTION_END_PATTERN, html[begin_idx:])
                if search_res is not None:
                    end_idx = begin_idx + search_res.end()
                    section_index = (begin_idx, end_idx)
                    section_indexes.append(section_index)
                else:
                    continue
            else:
                continue
        return section_indexes

    def merge_into_chunks(self, sections, html_front, html_back):
        groups = []
        if self.min_section_tokens is None and self.min_section_chars is None:
            groups = [[section] for section in sections]
        elif self.min_section_tokens is not None:
            lens = []
            for section in sections:
                tokens = section.text.split()
                lens.append(len(tokens))

            group = []
            cur_len = 0
            for i in range(0, len(sections)):
                group.append(sections[i])
                cur_len += lens[i]

                if i >= len(sections) - 1:
                    groups.append(group)
                elif cur_len >= self.min_section_tokens and (
                    lens[i + 1] >= self.min_section_tokens or (cur_len + lens[i + 1]) > sum(lens[i + 1 : i + 3])
                ):
                    groups.append(group)
                    group = []
                    cur_len = 0
                else:
                    continue
        elif self.min_section_chars is not None:
            lens = []
            for section in sections:
                lens.append(len(section.text))

            group = []
            cur_len = 0
            for i in range(0, len(sections)):
                group.append(sections[i])
                cur_len += lens[i]

                if i >= len(sections) - 1:
                    groups.append(group)
                elif cur_len >= self.min_section_chars and (
                    lens[i + 1] >= self.min_section_chars or (cur_len + lens[i + 1]) > sum(lens[i + 1 : i + 3])
                ):
                    groups.append(group)
                    group = []
                    cur_len = 0
                else:
                    continue
        else:
            char_lens = []
            token_lens = []
            for section in sections:
                char_lens.append(len(section.text))
                tokens = section.text.split()
                token_lens.append(len(tokens))

            group = []
            cur_char_len = 0
            cur_token_len = 0
            for i in range(0, len(sections)):
                group.append(sections[i])
                cur_char_len += char_lens[i]
                cur_token_len += token_lens[i]

                if i >= len(sections) - 1:
                    groups.append(group)
                elif (
                    cur_char_len >= self.min_section_chars
                    and (
                        char_lens[i + 1] >= self.min_section_chars
                        or (cur_char_len + char_lens[i + 1]) > sum(char_lens[i + 1 : i + 3])
                    )
                ) or (
                    cur_token_len >= self.min_section_tokens
                    and (
                        token_lens[i + 1] >= self.min_section_tokens
                        or (cur_token_len + token_lens[i + 1]) > sum(token_lens[i + 1 : i + 3])
                    )
                ):
                    groups.append(group)
                    group = []
                    cur_char_len = 0
                    cur_token_len = 0
                else:
                    continue

        chunks = []
        for group in groups:
            body = ""
            section_tag_ids = []
            for section in group:
                body += str(section)
                section_tag_ids.append(section.attrs["id"])

            chunk = html_front + body + html_back
            chunks.append(chunk)

        return chunks
