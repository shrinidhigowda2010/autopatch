"""Find code a user pasted into a chat message, so the assistant can scan it."""

from __future__ import annotations

import re

from app.ingest.languages import extension_for, guess_language

_FENCE = re.compile(r"```[ \t]*([\w+#.-]*)[ \t]*\n(.*?)```", re.DOTALL)
_FILENAME_COMMENT = re.compile(r"^\s*(?:#|//)\s*([\w./-]+\.[A-Za-z0-9]{1,6})\s*$")
# Unmistakable starts of code, allowed mid-sentence ("Find bugs in: def f(x): ...").
_STRONG_START = re.compile(
    r"(?:^|(?<=[:\s]))(async def \w+\(|def \w+\(|class \w+[:(]|function \w+\(|#include\s*<|"
    r"public (?:static |class )|func \w+\(|fn \w+\()"
)
# Weaker starts only count at the beginning of a line in a multi-line message.
_LINE_START = re.compile(r"(?m)^(import \w|from [\w.]+ import \w|const \w+ =|let \w+ =|package \w)")
_KEYWORD_LANGUAGE = (("async def", "Python"), ("def ", "Python"), ("class ", "Python"), ("import ", "Python"),
                     ("from ", "Python"), ("function ", "JavaScript"), ("const ", "JavaScript"),
                     ("let ", "JavaScript"), ("#include", "C++"), ("public ", "Java"), ("package ", "Go"),
                     ("func ", "Go"))

# Fence labels, mapped to the language names used across the ingest code.
_LANG_ALIASES = {
    "py": "Python", "python": "Python", "js": "JavaScript", "javascript": "JavaScript", "jsx": "JavaScript",
    "ts": "TypeScript", "typescript": "TypeScript", "tsx": "TypeScript", "java": "Java", "c": "C",
    "cpp": "C++", "c++": "C++", "cs": "C#", "csharp": "C#", "go": "Go", "rb": "Ruby", "ruby": "Ruby",
    "php": "PHP", "kotlin": "Kotlin", "swift": "Swift",
}


def extract_code(message: str) -> list[tuple[str, str]]:
    """Return [(filename, code)] for code in the message, or [] when there is none."""
    files: list[tuple[str, str]] = []
    for index, match in enumerate(_FENCE.finditer(message), start=1):
        lang, body = match.group(1).lower(), match.group(2)
        lines = body.strip("\n").split("\n")
        name = None
        if lines and (named := _FILENAME_COMMENT.match(lines[0])):
            name = named.group(1).split("/")[-1]
            lines = lines[1:]
        code = "\n".join(lines).strip("\n")
        if len(code.strip()) < 8:
            continue
        if not name:
            language = _LANG_ALIASES.get(lang) or _language(code)
            name = f"snippet_{index}{extension_for(language)}" if index > 1 else f"snippet{extension_for(language)}"
        files.append((name, code + "\n"))
    if files:
        return _unique(files)

    # No fences: look for where the code starts, e.g. "Find bugs in: def average(x): ..."
    start = _STRONG_START.search(message)
    if not start and "\n" in message.strip():
        start = _LINE_START.search(message)
    if not start:
        return []
    code = message[start.start(1):].strip()
    if len(code) < 12:
        return []
    return [(f"snippet{extension_for(_language(code))}", code + "\n")]


def _language(code: str) -> str:
    guessed = guess_language(code)
    if extension_for(guessed) != ".txt":
        return guessed
    for keyword, language in _KEYWORD_LANGUAGE:
        if code.startswith(keyword):
            return language
    return guessed


def _unique(files: list[tuple[str, str]]) -> list[tuple[str, str]]:
    seen: dict[str, int] = {}
    out = []
    for name, code in files:
        count = seen.get(name.lower(), 0)
        seen[name.lower()] = count + 1
        if count:
            stem, dot, ext = name.rpartition(".")
            name = f"{stem}_{count + 1}.{ext}" if dot else f"{name}_{count + 1}"
        out.append((name, code))
    return out
