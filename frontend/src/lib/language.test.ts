import { describe, expect, it } from "vitest";
import { extensionFor, guessLanguage, isArchiveName, looksLikeUrl } from "./language";

describe("guessLanguage", () => {
  it("spots Python", () => {
    expect(guessLanguage("def add(a, b):\n    return a + b\n")).toBe("Python");
  });
  it("spots Java", () => {
    expect(guessLanguage('public class Main { public static void main(String[] a) { System.out.println(1); } }')).toBe("Java");
  });
  it("spots TypeScript over JavaScript", () => {
    expect(guessLanguage("const n: number = 3;\nconsole.log(n);")).toBe("TypeScript");
  });
  it("falls back to text", () => {
    expect(guessLanguage("hello there")).toBe("Text");
    expect(extensionFor("Text")).toBe(".txt");
  });
});

describe("helpers", () => {
  it("recognises links and archives", () => {
    expect(looksLikeUrl("https://github.com/a/b")).toBe(true);
    expect(looksLikeUrl("print('https://x')")).toBe(false);
    expect(isArchiveName("project.tar.gz")).toBe(true);
    expect(isArchiveName("notes.pdf")).toBe(false);
  });
});
