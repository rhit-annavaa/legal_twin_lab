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

- **Profile research** — for each named person, Claude actually searches the public record
  (published opinions, news coverage, firm/court bios, articles) and compiles a structured
  profile: bio, documented tendencies, notable cases, and sources. Every tendency and case is
  tagged with the specific URL it came from, or marked `[unverified — model-generated]` if it's a
  plausible inference the research step didn't find directly documented — that tag is visible both
  in the editable text boxes and inside the persona's own grounding, so a documented ruling
  pattern is never presented to (or by) the simulation as indistinguishable from a guess. You can
  edit or override anything before running a session.
- **Simulated proceeding** — the pipeline hard-branches on proceeding type, because a motion
  hearing and a jury trial hand the decision to different people under different rules:
  - **Motion hearing** (no jury exists): opening/argument rounds → closings → the judge privately
    deliberates and then rules directly on the motion. This is the only path where a judge decides
    the merits.
  - **Full trial**: opening statements → N rounds of argument/rebuttal (the judge may ask a
    clarifying question or note a procedural/evidentiary point during this phase, but never
    comments on who's winning or previews an outcome) → closings → a **separate jury verdict
    step**, where the judge first prepares a special verdict form and the jury answers only those
    specific questions (yes/no per claim, willfulness, a damages figure) with no narrative
    reasoning, exactly like a real verdict form → **post-trial motions** from both counsel (JMOL,
    injunction, enhancement, fees, remittitur) → a **separate post-verdict judge step** that treats
    the verdict as fixed: the judge can only set aside a jury finding if a party actually moved for
    JMOL on it and the "no reasonable jury" standard is met; otherwise the order is confined to
    equitable relief (the eBay four-factor test or its analog), discretionary enhancement based on
    the jury's willfulness finding, fee-shifting, and remittitur.
- **Live transcript** — everything streams into the browser turn by turn as it's generated.
- **Run logging + variance check** — every run is written to `runs/<run_id>.json` (full transcript
  + structured outcome) so it can be reopened later. The Anthropic API has no seed parameter, so
  there's no way to force one exact run to reproduce — instead, "Run N times & compare" on the
  sidebar re-runs the same configuration back-to-back and reports the spread of jury findings
  (exact, since those are structured) and a rough keyword-based read on the post-verdict order
  (not exact — read the raw per-run text for anything that matters). Don't treat a single
  transcript as a signal; treat it as one sample.

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
   incomplete or wrong, especially for less-documented people. Check which tendencies carry a
   `[source: ...]` tag versus `[unverified — model-generated]` before you trust them.
2. Edit the bio, tendencies, sources, or add your own notes in the "Your notes" box — manual notes
   are passed to the model as overriding/supplementing context. Anything you type into the
   tendencies box by hand (with no `[source: ...]` tag) is treated as unverified, same as an
   unsourced research result.
3. Describe the case: facts, procedural posture, what's actually at issue. This can be a real
   matter's facts or a fully hypothetical fact pattern — the agents argue from this plus general
   legal knowledge.
4. Choose proceeding type and number of argument rounds, then **Begin proceeding**. Choosing "Full
   trial" gets you the jury verdict → post-trial motions → post-verdict order sequence; "Motion
   hearing" goes straight to a bench ruling since there's no jury.
5. Watch the transcript stream in. The judge's internal reasoning trace (motion hearings only) is
   collapsed by default — click "show internal reasoning" to expand it. The jury verdict, any
   post-trial motions, and the final ruling/order are visually highlighted.
6. Optionally click **Run N times & compare** to re-run the same configuration a few times and see
   the spread of jury findings rather than trusting one transcript.

Researched profiles are cached to `profiles/<name>.json` so you don't re-research the same person
every run — delete a file there (or click "Research public record" again) to refresh it. Every
proceeding (single run or part of a batch) is logged to `runs/<run_id>.json` with its full
transcript and structured outcome.

## 4. Extending it

- **Feed in real documents**: paste excerpts from actual briefs, motions, or prior rulings into the
  case description box — the agents will treat them as case context.
- **Change the procedure**: `models/courtroom.py` is a set of straightforward generator/helper
  functions branching on `case_type` — add phases (e.g., cross-examination, amicus input, an
  appeal stage), change round structure, or add more parties. Keep new phases honest about which
  decision-maker actually has the power to do what in real procedure before wiring them in.
- **Swap models per role**: set `JUDGE_MODEL` / `COUNSEL_MODEL` / `RESEARCH_MODEL` / `JURY_MODEL`
  independently in `.env` — e.g. a stronger model for the judge's reasoning, a faster one for
  counsel or the jury.
- **Tune batch size**: `MAX_BATCH_RUNS` in `.env` caps how many repetitions "Run N times & compare"
  will execute in one request, since each repetition re-runs the whole multi-call pipeline
  synchronously.

## 5. Responsible use

- Treat every output as a **grounded guess**, not a verified fact about the real person — profiles
  are built from public information Claude could find, which may be incomplete, outdated, or
  wrong, and are now explicitly tagged per-item as sourced or unverified so you can tell which is
  which at a glance.
- Don't present, file, share externally, or attribute any generated text as an actual statement,
  argument, or ruling made by the real named individual.
- Be thoughtful about simulating currently-sitting judges or opposing counsel on a live, active
  matter — this tool is meant for strategy testing and training, not for anything that could be
  mistaken for surveillance or profiling of a specific person tied to a real pending case.
- The jury verdict and judge's ruling/order are a prediction exercise, not legal advice, and
  shouldn't be the basis for a real legal decision on their own — and a single simulated run should
  never be treated as more predictive than it is; that's what the batch variance check is for.
