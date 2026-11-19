# Three-minute walkthrough

Use the home page. Leave `GEMINI_API_KEY` empty if you want to show that the product does not depend on the network. The footer status will read **AI engine: standby** — analysis still runs.

## 0:00 — Open the marks calculator

On the home page, under **Explore example projects**, click **Marks calculator**. Say: this is a classic buggy marks program. It should reject marks below 0 and above 100. The scan starts on its own.

## 0:25 — Scan

Point at the file tree, the language, the empty dependency list, and the import graph. When the bugs appear, point at the two findings: marks outside 0–100, and the crash on an empty list. Mention the tool line at the bottom so judges see pylint and bandit actually ran.

## 0:55 — Explain

Open the marks bug. Read the root cause and the trigger: type -5 or 150. Toggle **Student mode** and show the shorter sentence. Switch the language to ಕನ್ನಡ or हिन्दी for one sentence, then back to English.

## 1:25 — Fix

Open Fix. Show Ask Every Fix mode, the red before and the green after, and the unified diff. Do not approve yet. Say the original upload is untouched.

## 1:40 — Test

Open Test and click **Run before and after**. The list updates live. Say what each block means: existing tests, generated edge tests before and after, and the regression suite.

## 2:15 — Approve

Go back to Fix. Approve one fix (or use Apply all safe fixes after the pre-flight list). Say risky or low-confidence patches stay for a person.

## 2:35 — Dashboard, history, export

Open Dashboard and show the health score and charts. Open History / Decision Log and download the PDF or the zip. Say the zip is the workspace after accepted patches.

## 2:50 — Benchmark

Open Benchmark. The table is the last measured run: 8 projects, 12 bugs, 100% detection, 100% fix success, 0 false positives.

## If something fails

Stay on the marks calculator. Static analysis and project knowledge do not need a network. If a test run is slow, the event list will keep moving.
