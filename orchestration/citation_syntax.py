"""Citation positions in the Markdown subset rendered by MarkdownAnswer.

Inline parsing respects block and table-cell boundaries. The shared JSON
fixtures exercise this contract against the actual frontend renderer.
"""
from __future__ import annotations

import re

BRACKETS = re.compile(r'\[([^\[\]\x00]+)\]')
CANONICAL_GROUP = re.compile(r'[A-Za-z0-9_:.-]+(?:\s*[,;]\s*[A-Za-z0-9_:.-]+)*\Z')
INLINE_NON_CITATIONS = re.compile(r'`[^`]+`|\[[^\]]+\]\([^)]+\)')
TABLE_SEPARATOR = re.compile(r'^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$')
HEADING = re.compile(r'^(#{1,4})\s+')
LIST = re.compile(r'^\s*(?:[-*]|\d+[.)])\s+')


def citation_text(answer: str) -> str:
    """Mask non-citation regions while retaining original character offsets."""
    lines = answer.splitlines(keepends=True)
    offsets, cursor = [], 0
    for line in lines:
        offsets.append(cursor)
        cursor += len(line)
    masked = ['\x00'] * len(answer)

    def inline(ranges):
        if not ranges:
            return
        start, end = ranges[0][0], ranges[-1][1]
        segment = [' '] * (end - start)
        for left, right in ranges:
            segment[left-start:right-start] = answer[left:right]
        text = INLINE_NON_CITATIONS.sub(lambda m: ' ' * len(m[0]), ''.join(segment))
        masked[start:end] = text

    def body(index, prefix=0):
        line = lines[index]
        left = len(line) - len(line.lstrip()) + prefix
        return offsets[index] + left, offsets[index] + len(line.rstrip())

    def table(index):
        return index + 1 < len(lines) and '|' in lines[index] and TABLE_SEPARATOR.fullmatch(lines[index+1].strip())

    def cells(index):
        left, right = body(index)
        if answer[left:right].startswith('|'):
            left += 1
        if answer[left:right].endswith('|'):
            right -= 1
        boundaries = [left-1, *[p for p in range(left, right) if answer[p] == '|'], right]
        return [(a+1, b) for a, b in zip(boundaries, boundaries[1:])]

    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if not stripped:
            i += 1
        elif stripped.startswith('```'):
            i += 1
            while i < len(lines) and not lines[i].strip().startswith('```'):
                i += 1
            i += 1
        elif HEADING.match(stripped):
            inline([body(i, HEADING.match(stripped).end())])
            i += 1
        elif table(i):
            headers = cells(i)
            for cell in headers:
                inline([cell])
            i += 2
            while i < len(lines) and lines[i].strip() and '|' in lines[i]:
                for cell in cells(i)[:len(headers)]:
                    inline([cell])
                i += 1
        elif LIST.match(stripped):
            inline([body(i, LIST.match(stripped).end())])
            i += 1
        elif stripped.startswith('>'):
            ranges = []
            while i < len(lines) and lines[i].strip().startswith('>'):
                ranges.append(body(i, re.match(r'^>\s?', lines[i].strip()).end()))
                i += 1
            inline(ranges)
        else:
            ranges = [body(i)]
            i += 1
            while i < len(lines):
                line = lines[i].strip()
                if not line or line.startswith(('```', '>')) or HEADING.match(line) or LIST.match(line) or table(i):
                    break
                ranges.append(body(i))
                i += 1
            inline(ranges)
    return ''.join(masked)


def citation_matches(answer: str):
    return BRACKETS.finditer(citation_text(answer))


def canonical_tokens(answer: str) -> list[dict]:
    tokens = []
    for match in citation_matches(answer):
        if not CANONICAL_GROUP.fullmatch(match[1]):
            continue
        for identity in re.split(r'[,;]', match[1]):
            tokens.append({'citation_id': identity.strip(), 'raw': match[0], 'position': match.start()})
    return tokens
