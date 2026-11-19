/**
 * Syntax highlighter with only the languages students actually paste.
 * The full Prism build is ~600 KB; this keeps the assistant chunk small.
 */
import { PrismLight } from "react-syntax-highlighter";
import bash from "react-syntax-highlighter/dist/esm/languages/prism/bash";
import c from "react-syntax-highlighter/dist/esm/languages/prism/c";
import cpp from "react-syntax-highlighter/dist/esm/languages/prism/cpp";
import csharp from "react-syntax-highlighter/dist/esm/languages/prism/csharp";
import css from "react-syntax-highlighter/dist/esm/languages/prism/css";
import diff from "react-syntax-highlighter/dist/esm/languages/prism/diff";
import go from "react-syntax-highlighter/dist/esm/languages/prism/go";
import java from "react-syntax-highlighter/dist/esm/languages/prism/java";
import javascript from "react-syntax-highlighter/dist/esm/languages/prism/javascript";
import json from "react-syntax-highlighter/dist/esm/languages/prism/json";
import jsx from "react-syntax-highlighter/dist/esm/languages/prism/jsx";
import markup from "react-syntax-highlighter/dist/esm/languages/prism/markup";
import php from "react-syntax-highlighter/dist/esm/languages/prism/php";
import python from "react-syntax-highlighter/dist/esm/languages/prism/python";
import rust from "react-syntax-highlighter/dist/esm/languages/prism/rust";
import sql from "react-syntax-highlighter/dist/esm/languages/prism/sql";
import tsx from "react-syntax-highlighter/dist/esm/languages/prism/tsx";
import typescript from "react-syntax-highlighter/dist/esm/languages/prism/typescript";

const LANGUAGES: Record<string, unknown> = {
  bash, c, cpp, csharp, css, diff, go, java, javascript, json, jsx, markup, php, python, rust, sql, tsx, typescript,
};
const ALIASES: Record<string, string> = {
  py: "python", js: "javascript", ts: "typescript", sh: "bash", shell: "bash", html: "markup", xml: "markup", cs: "csharp", rs: "rust",
};

for (const [name, grammar] of Object.entries(LANGUAGES)) {
  PrismLight.registerLanguage(name, grammar);
}
for (const [alias, name] of Object.entries(ALIASES)) {
  PrismLight.registerLanguage(alias, LANGUAGES[name]);
}

export default PrismLight;
