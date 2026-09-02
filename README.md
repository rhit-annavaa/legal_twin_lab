# Legal Twin Simulation Lab

An internal prototype for simulating an adversarial legal proceeding: two "counsel" personas and a
"judge" persona, each grounded in a publicly-researched profile of a real (or hypothetical) legal
professional, argue a case and the judge issues a reasoned, simulated ruling.

**This tool is for internal testing and strategy exploration only.** Every persona output is an
AI-generated *prediction*, built from publicly available information plus general legal reasoning —
it is never an actual statement, filing, or ruling by the real person, and should never be
represented as one (see "Responsible use" below).

---

## 1. What it does

- **Profile research** — for each named person, Claude searches the public record (published
  opinions, news coverage, firm/court bios, articles) and compiles a structured profile: bio,
  documented tendencies, notable cases, and sources. You can then edit or override anything before
  running a session.
- **Simulated proceeding** — a judge and two counsel personas run through a real courtroom-style
  sequence: opening statements → N rounds of argument/rebuttal (with optional judge questions) →
  closing arguments → the judge's private deliberation (a visible reasoning trace) → a final ruling.
- **Live transcript** — everything streams into the browser turn by turn as it's generated.

## 2. One-time setup

You'll need Python 3.10+ installed. Everything below is run from a terminal.

**Step 1 — Get an Anthropic API key**
Go to <https://console.anthropic.com/settings/keys>, sign in (or create an account), and create a
new API key. Note that API usage is billed separately from any Claude.ai subscription — check
<https://console.anthropic.com/settings/billing> to add credit if needed.

**Step 2 — Unzip the project and open a terminal in that folder**

**Step 3 — Create a virtual environment and install dependencies**
```bash
python3 -m venv venv
source venv/bin/activate        # on Windows: venv\Scripts\activate
pip install -r requirements.txt
```

**Step 4 — Add your API key**
```bash
cp .env.example .env
```
Open `.env` in any text editor and paste your key in place of `sk-ant-your-key-here`. You can
optionally change which model plays each role (judge / counsel / researcher) in the same file —
any current Claude model string works, e.g. `claude-opus-5`, `claude-sonnet-5`.

**Step 5 — Run the server**
```bash
uvicorn app:app --reload
```
Then open **http://127.0.0.1:8000** in your browser.

## 3. Using it

1. Enter the judge's and each counsel's full name (add a court/firm hint if the name is common),
   then click **Research public record** for each. Review what comes back — auto-research can be
   incomplete or wrong, especially for less-documented people.
2. Edit the bio, tendencies, sources, or add your own notes in the "Your notes" box — manual notes
   are passed to the model as overriding/supplementing context.
3. Describe the case: facts, procedural posture, what's actually at issue. This can be a real
   matter's facts or a fully hypothetical fact pattern — the agents argue from this plus general
   legal knowledge.
4. Choose proceeding type and number of argument rounds, then **Begin proceeding**.
5. Watch the transcript stream in. The judge's internal reasoning trace is collapsed by default —
   click "show internal reasoning" to expand it. The final ruling is highlighted at the bottom.

Researched profiles are cached to `profiles/<name>.json` so you don't re-research the same person
every run — delete a file there (or click "Research public record" again) to refresh it.

## 4. Extending it

- **Feed in real documents**: paste excerpts from actual briefs, motions, or prior rulings into the
  case description box — the agents will treat them as case context.
- **Change the procedure**: `models/courtroom.py` is a straightforward generator function — add
  phases (e.g., cross-examination, amicus input), change round structure, or add more parties.
- **Swap models per role**: set `JUDGE_MODEL` / `COUNSEL_MODEL` / `RESEARCH_MODEL` independently in
  `.env` — e.g. a stronger model for the judge's reasoning, a faster one for counsel.
- **Persist sessions**: right now each run streams to the browser and isn't saved; you could add a
  simple write-to-disk step in `app.py`'s `event_stream()` if you want a session log.

## 5. Responsible use

- Treat every output as a **grounded guess**, not a verified fact about the real person — profiles
  are built from public information Claude could find, which may be incomplete, outdated, or wrong.
- Don't present, file, share externally, or attribute any generated text as an actual statement,
  argument, or ruling made by the real named individual.
- Be thoughtful about simulating currently-sitting judges or opposing counsel on a live, active
  matter — this tool is meant for strategy testing and training, not for anything that could be
  mistaken for surveillance or profiling of a specific person tied to a real pending case.
- The judge persona's "ruling" is a prediction exercise, not legal advice, and shouldn't be the
  basis for a real legal decision on its own.
