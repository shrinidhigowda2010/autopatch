# FixPilot: 5-minute judge demo

**URL:** https://autopatch-7yyu.onrender.com (or http://127.0.0.1:8000 locally)
**Before you start:** sign in once so the Coder ID shows up, and keep a second tab open on `/race`. Have one screenshot of buggy code ready on the desktop.

| Time | Screen | What you do | What you say |
| --- | --- | --- | --- |
| 0:00 | Home | Move the mouse over the 3D code slab while the lines turn red → green and the shield rises. Point at the counter strip. | "FixPilot finds bugs, explains them, fixes them and proves the fix, with a person approving every change. These counters come from our real benchmark: 12 of 12 bugs found, 12 of 12 fixed, 0 false positives." |
| 0:30 | Home → Scan | Click **Marks calculator**. The scan starts by itself. | "This is the example from the problem statement: marks below 0 or above 100 are accepted, and an empty list crashes it." |
| 0:50 | Scan | Point at the file tree, the tool line (pylint, bandit…) and the findings with severity and confidence. | "Two layers run in parallel: real static tools and Gemini. If Gemini is down, the static layer still works." |
| 1:15 | Explain | Open the range bug. Read the trigger (-5 or 150). Toggle **Student mode**, then switch to ಕನ್ನಡ for one line. | "We explain the input that triggers the bug, not just a line number, in simple words and local languages." |
| 1:45 | Fix | Show the red/green diff and the risk badge. Click **Approve**. | "The patch is minimal. Nothing is written until I approve. After approval the tests re-run, and a failure rolls the change back automatically." |
| 2:10 | Fix → Prove it | Click **🛡 Break-It attack**, then **⚖️ AI Debate Room**. | "Break-It throws 15 hostile inputs at the old and new code: the old code fails, the new code survives. In the Debate Room one AI attacks the fix, another defends it, and a judge gives a verdict." |
| 2:50 | Test | Click **Run before and after**. | "Existing tests, generated edge cases before and after, and a regression run, all inside a sandbox with no secrets and strict limits." |
| 3:20 | Assistant | Open **Assistant**. Show the greeting, pick **Review** mode, attach the screenshot (or click a suggestion chip). When it replies, click 👍. | "It's a project-aware chat: it reads screenshots, accepts voice in three languages, and shows a patch card that goes through the same approval flow. Feedback is stored." |
| 4:00 | `/race` tab | Paste `def average(m): return sum(m)/len(m)` and press **Start the race**. | "The Live Repair Race runs the real pipeline: bug found, fixed, verified, in about 8 seconds." |
| 4:30 | History → Benchmark | Show the Decision Log with the Coder ID, click **Export PDF**, then open **Benchmark**. | "Every decision is logged against my Coder ID and exported as a report. The benchmark is reproducible with one command." |
| 4:50 | Wrap up | Back on Home. | "Detect, repair, verify, with a human in charge. That's FixPilot." |

## If something goes wrong

- **Gemini is slow or offline:** keep going. The scan, patches, tests, Break-It and Race all work on the static layer. The footer shows *AI engine: standby*.
- **The first AI call is slow:** the primary model can take a few seconds to warm up. Talk over the tool line while it runs.
- **Free-tier cold start (Render):** open the URL a minute before the demo.
- **Break-It shows a note instead of a scoreboard:** it works on Python functions. Stay on the marks calculator.
