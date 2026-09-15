"""Request-local generation labels; persisted citations retain canonical IDs."""
from __future__ import annotations

from dataclasses import dataclass
import re
from types import MappingProxyType
from typing import Mapping

from orchestration.citation_syntax import citation_matches, citation_text


BRACKETS = re.compile(r"\[([^\[\]]+)\]")
ALIAS = re.compile(r"\bS[0-9]+\b")
IDENTIFIER = re.compile(r"[A-Za-z0-9_:.-]{1,200}\Z")


class InvalidCitationAlias(ValueError):
    """Generation referenced a label absent from this request's evidence."""


@dataclass(frozen=True)
class CitedPrompt:
    prompt: str
    aliases: Mapping[str, str]

    def resolve(self, answer: str) -> str:
        canonical_ids = set(self.aliases.values())
        if re.search(r"\[[^\[\]]*\bS[0-9]+\b[^\[\]]*$", citation_text(answer)):
            raise InvalidCitationAlias("Incomplete generation citation label")

        def replace(match):
            tokens = [token.strip() for token in re.split(r"[,;]", match[1])]
            expanded = []
            for token in tokens:
                range_match = re.fullmatch(r'S([1-9][0-9]*)\s*[-–—]\s*S([1-9][0-9]*)', token)
                if range_match:
                    start, end = map(int, range_match.groups())
                    if end < start or end - start + 1 > min(100, len(self.aliases)):
                        raise InvalidCitationAlias("Invalid generation citation range")
                    labels = [f'S{number}' for number in range(start, end + 1)]
                    if any(label not in self.aliases for label in labels):
                        raise InvalidCitationAlias("Citation range includes an unknown label")
                    expanded.extend(labels)
                else:
                    expanded.append(token)
            if len(expanded) > 100:
                raise InvalidCitationAlias("Excessive citation group")
            resolved = []
            changed = False
            for token in expanded:
                if token in self.aliases:
                    resolved.append(self.aliases[token])
                    changed = True
                elif token in canonical_ids:
                    resolved.append(token)
                elif ALIAS.search(token):
                    raise InvalidCitationAlias("Unrecognized generation citation label")
                else:
                    # Preserve other bracket text for the existing citation audit.
                    resolved.append(token)
            return "[" + ", ".join(resolved) + "]" if changed else match[0]

        parts, cursor = [], 0
        for match in citation_matches(answer):
            parts.extend((answer[cursor:match.start()], replace(match)))
            cursor = match.end()
        parts.append(answer[cursor:])
        return ''.join(parts)


def prepare_citations(prompt: str, *document_groups: list[dict]) -> CitedPrompt:
    """Shorten only known bracketed IDs, never query text or arbitrary hashes.

    Labels already present in the prompt or canonical IDs are reserved to avoid
    collisions. The map is local to one request and is not a model instruction.
    """
    identities = dict.fromkeys(
        str(row.get("doc_id") or row.get("id") or "")
        for group in document_groups for row in group
    )
    reserved = set(ALIAS.findall(prompt)) | set(identities)
    aliases = {}
    for identity in identities:
        if not IDENTIFIER.fullmatch(identity):
            continue
        # Only headers surviving prompt bounds can introduce a citation target.
        if f"\n[{identity}] (" not in prompt:
            continue
        number = len(aliases) + 1
        while f"S{number}" in reserved:
            number += 1
        label = f"S{number}"
        reserved.add(label)
        aliases[label] = identity
    reverse = {identity: label for label, identity in aliases.items()}

    # Keep the user question verbatim, including any IDs it explicitly mentions.
    evidence, separator, question = prompt.rpartition("<user_question>")
    if not separator:
        evidence, question = prompt, ""
    shortened = BRACKETS.sub(
        lambda match: "[" + reverse[match[1]] + "]" if match[1] in reverse else match[0],
        evidence,
    )
    if aliases:
        example = ", ".join(list(aliases)[:2])
        shortened += (
            "\nCITATION FORMAT: Cite the short source labels shown in evidence "
            f"headers, for example [{example}]. This applies to primary, "
            "linked, analysis, and reliability evidence and replaces the "
            "doc_id/analysis_*/reliability_* citation format above. Use only "
            "labels present in the supplied evidence. Do not expand labels "
            "into hashes or invent labels. Reserve square brackets for source "
            "citations; put taxonomic ranks and other notes in parentheses. "
            "Use simple Markdown without HTML.\n"
        )
    return CitedPrompt(shortened + separator + question, MappingProxyType(aliases))
