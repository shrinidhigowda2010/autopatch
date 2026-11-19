"""File extensions FixPilot understands, and a best guess for code with no filename."""

from __future__ import annotations

import re
from pathlib import PurePosixPath

CODE_LANGUAGES = {
    ".py": "Python",
    ".js": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".jsx": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".java": "Java",
    ".c": "C",
    ".h": "C",
    ".cpp": "C++",
    ".cc": "C++",
    ".cxx": "C++",
    ".hpp": "C++",
    ".cs": "C#",
    ".go": "Go",
    ".rb": "Ruby",
    ".php": "PHP",
    ".kt": "Kotlin",
    ".kts": "Kotlin",
    ".swift": "Swift",
    ".rs": "Rust",
    ".scala": "Scala",
    ".dart": "Dart",
    ".lua": "Lua",
    ".r": "R",
    ".pl": "Perl",
    ".sh": "Shell",
    ".bash": "Shell",
    ".ps1": "PowerShell",
    ".sql": "SQL",
    ".html": "HTML",
    ".htm": "HTML",
    ".css": "CSS",
    ".scss": "SCSS",
    ".vue": "Vue",
    ".svelte": "Svelte",
}

TEXT_LANGUAGES = {
    ".json": "JSON",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".xml": "XML",
    ".md": "Markdown",
    ".txt": "Text",
    ".toml": "TOML",
    ".ini": "INI",
    ".cfg": "INI",
    ".csv": "CSV",
    ".gradle": "Gradle",
    ".env": "Env",
}

LANGUAGES = {**CODE_LANGUAGES, **TEXT_LANGUAGES}
TEXT_NAMES = {"dockerfile", "makefile", "procfile", "gemfile", "rakefile", "license", "readme"}

# Extension for each language a guess can return.
_EXTENSION = {
    "Python": ".py",
    "JavaScript": ".js",
    "TypeScript": ".ts",
    "Java": ".java",
    "C": ".c",
    "C++": ".cpp",
    "C#": ".cs",
    "Go": ".go",
    "Ruby": ".rb",
    "PHP": ".php",
    "Kotlin": ".kt",
    "Swift": ".swift",
    "Rust": ".rs",
    "Shell": ".sh",
    "SQL": ".sql",
    "HTML": ".html",
    "CSS": ".css",
    "JSON": ".json",
    "Text": ".txt",
}

# (language, pattern, weight). The language with the highest total wins.
_SIGNS: list[tuple[str, str, int]] = [
    ("Python", r"^\s*def \w+\(.*\)\s*(->\s*[\w\[\], .]+)?:\s*$", 4),
    ("Python", r"^\s*(from [\w.]+ )?import [\w., ]+$", 2),
    ("Python", r"^\s*(if|elif|for|while|with|try|except|else)\b.*:\s*$", 2),
    ("Python", r"\bprint\(|\bself\.|__name__ == ['\"]__main__['\"]", 2),
    ("Java", r"\bpublic (static )?(class|void|int|String)\b", 4),
    ("Java", r"System\.out\.println|import java\.", 5),
    ("C#", r"using System;|Console\.Write(Line)?\(|namespace \w+", 5),
    ("C++", r"#include\s*<(iostream|vector|string|map)>|std::|cout\s*<<", 5),
    ("C", r"#include\s*<(stdio|stdlib|string)\.h>|\bprintf\(|\bmalloc\(", 4),
    ("Go", r"^package \w+|\bfunc \w*\(|fmt\.\w+\(|:= ", 4),
    ("Rust", r"\bfn \w+\(|\blet mut\b|println!\(|impl \w+", 5),
    ("PHP", r"<\?php|\$\w+\s*=|echo \$", 5),
    ("Ruby", r"^\s*puts |^\s*end\s*$|\.each do \|", 3),
    ("Kotlin", r"\bfun \w+\(|\bval \w+\s*=", 4),
    ("Swift", r"import (UIKit|SwiftUI|Foundation)|\bguard let\b|\bfunc \w+\(.*\)\s*->", 4),
    ("TypeScript", r":\s*(string|number|boolean|any)\b|\binterface \w+\s*\{|\btype \w+\s*=", 4),
    ("JavaScript", r"\bfunction \w*\(|\b(const|let|var) \w+\s*=|=>|console\.log\(|require\(", 3),
    ("Shell", r"^#!/bin/(ba)?sh|^\s*echo |^\s*fi\s*$|\$\{?\w+\}?", 2),
    ("SQL", r"(?i)\b(select .+ from|insert into|create table|update \w+ set)\b", 5),
    ("HTML", r"(?i)<!doctype html|<html|<div\b|<body\b", 5),
    ("CSS", r"^\s*[.#]?[\w-]+\s*\{\s*$|^\s*[\w-]+:\s*[^;]+;\s*$", 2),
]


def language_for(path: str) -> str:
    name = PurePosixPath(path).name.lower()
    suffix = PurePosixPath(name).suffix
    if suffix in LANGUAGES:
        return LANGUAGES[suffix]
    if name in TEXT_NAMES or name.startswith(".env"):
        return "Text"
    return "Other"


def guess_language(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        return "Text"
    if stripped[0] in "{[":
        try:
            import json

            json.loads(stripped)
            return "JSON"
        except ValueError:
            pass
    scores: dict[str, int] = {}
    lines = stripped.splitlines()[:400]
    for language, pattern, weight in _SIGNS:
        regex = re.compile(pattern, re.MULTILINE)
        hits = sum(1 for line in lines if regex.search(line))
        if hits:
            scores[language] = scores.get(language, 0) + weight * min(hits, 5)
    if scores.get("TypeScript") and scores.get("JavaScript"):
        scores["TypeScript"] += scores["JavaScript"]
    if not scores:
        return "Text"
    return max(scores, key=scores.get)


def extension_for(language: str) -> str:
    return _EXTENSION.get(language, ".txt")


def is_code(path: str) -> bool:
    return PurePosixPath(path).suffix.lower() in CODE_LANGUAGES
