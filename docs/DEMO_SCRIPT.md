# Three-minute demo

Use the home page. Leave `GEMINI_API_KEY` empty if you want to show that the demo does not depend on the network. Say that out loud: the banner will read "Demo mode".

## 0:00 — Open the marks calculator

On the home page, click **Marks calculator**. Say: this is the program from the problem statement. It should reject marks below 0 and above 100. The scan starts on its own.

## 0:25 — Scan

Point at the file tree, the language, the empty dependency list, and the import graph. When the bugs appear, point at the two findings: marks outside 0–100, and the crash on an empty list. Mention the tool line at the bottom so the judges see pylint and bandit actually ran. If the banner is up, say the model notes are cached and labelled, and the detectors themselves ran just now.

## 0:55 — Explain

Open the marks bug. Read the root cause and the trigger: type -5 or 150. Toggle **Student mode** and show the shorter sentence. Switch the language to ಕನ್ನಡ or हिन्दी for one sentence, then back to English.

## 1:25 — Fix

Open Fix. Show the red before and the green after, and the unified diff under them. Do not accept yet. Say the file on disk has not changed.

## 1:40 — Test

Open Test and click **Run before and after**. The list updates live. Say what each block means: existing tests passed even on the buggy code, the generated edge tests failed before the patch, they passed after, and the full suite passed as a regression. Point at normal, min, max, and invalid in the pytest names if the output is on screen.

## 2:15 — Approve

Go back to Fix. Click **Apply all safe fixes**. Say this button only writes patches that are high confidence and whose tests passed. The skipped-first-row sample would be held back because its confidence is under 80 percent; you can mention that if you have ten seconds.

## 2:35 — Dashboard, history, export

Open Dashboard and show the severity chart. Open History and download the PDF or the zip. Say the zip is the workspace after the accepted patches, not the original upload.

## 2:50 — Benchmark

Open Benchmark. The table is the last measured run: 8 projects, 12 bugs, 100% detection, 100% fix success, 0 false positives. Offer to press **Run benchmark** if a judge wants it re-measured. It takes about a minute and does not call Gemini.

## If something fails

Stay on the marks calculator. The static scan and the cached notes do not need a network. If a test run is slow, it is pytest starting under the sandbox limits; the event list will keep moving.
