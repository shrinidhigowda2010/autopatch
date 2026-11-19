// A quick guess at the language of pasted code, so the paste tab can name the file.
// The backend makes its own guess too; this one is only for the label and filename.

type Sign = [language: string, pattern: RegExp, weight: number];

const SIGNS: Sign[] = [
  ["Python", /^\s*def \w+\(.*\)\s*(->\s*[\w[\], .]+)?:\s*$/m, 4],
  ["Python", /^\s*(from [\w.]+ )?import [\w., ]+$/m, 2],
  ["Python", /^\s*(if|elif|for|while|with|try|except|else)\b.*:\s*$/m, 2],
  ["Python", /\bprint\(|\bself\./, 2],
  ["Java", /\bpublic (static )?(class|void|int|String)\b|System\.out\.println/, 5],
  ["C#", /using System;|Console\.Write(Line)?\(/, 5],
  ["C++", /#include\s*<(iostream|vector|string)>|std::|cout\s*<</, 5],
  ["C", /#include\s*<(stdio|stdlib|string)\.h>|\bprintf\(/, 4],
  ["Go", /^package \w+|\bfunc \w*\(|fmt\.\w+\(/m, 4],
  ["Rust", /\bfn \w+\(|\blet mut\b|println!\(/, 5],
  ["PHP", /<\?php/, 6],
  ["Ruby", /^\s*puts |^\s*end\s*$/m, 3],
  ["Kotlin", /\bfun \w+\(|\bval \w+\s*=/, 4],
  ["TypeScript", /:\s*(string|number|boolean)\b|\binterface \w+\s*\{/, 4],
  ["JavaScript", /\bfunction \w*\(|\b(const|let|var) \w+\s*=|=>|console\.log\(/, 3],
  ["SQL", /\b(select .+ from|insert into|create table)\b/i, 5],
  ["HTML", /<!doctype html|<html|<div\b/i, 5],
  ["Shell", /^#!\/bin\/(ba)?sh|^\s*echo /m, 3],
];

const EXTENSIONS: Record<string, string> = {
  Python: ".py",
  JavaScript: ".js",
  TypeScript: ".ts",
  Java: ".java",
  "C#": ".cs",
  "C++": ".cpp",
  C: ".c",
  Go: ".go",
  Rust: ".rs",
  PHP: ".php",
  Ruby: ".rb",
  Kotlin: ".kt",
  SQL: ".sql",
  HTML: ".html",
  Shell: ".sh",
  Text: ".txt",
};

export function guessLanguage(code: string): string {
  if (!code.trim()) return "Text";
  const scores: Record<string, number> = {};
  for (const [language, pattern, weight] of SIGNS) {
    if (pattern.test(code)) scores[language] = (scores[language] ?? 0) + weight;
  }
  if (scores.TypeScript && scores.JavaScript) scores.TypeScript += scores.JavaScript;
  const best = Object.entries(scores).sort((a, b) => b[1] - a[1])[0];
  return best ? best[0] : "Text";
}

export function extensionFor(language: string): string {
  return EXTENSIONS[language] ?? ".txt";
}

export function looksLikeUrl(text: string): boolean {
  return /^https?:\/\/\S+$/i.test(text.trim());
}

const ARCHIVES = [".zip", ".tar", ".tar.gz", ".tgz"];

export function isArchiveName(name: string): boolean {
  const lowered = name.toLowerCase();
  return ARCHIVES.some((suffix) => lowered.endsWith(suffix));
}
