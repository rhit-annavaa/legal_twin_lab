import json
import re
import uuid

import config
from .agent import PersonaAgent, JuryPanel
from .profile import Profile
from .runlog import persist_run

JMOL_KEYWORDS = ("jmol", "judgment as a matter of law", "judgment notwithstanding", "jnov")


def _mentions_jmol(text: str) -> bool:
    t = (text or "").lower()
    return any(k in t for k in JMOL_KEYWORDS)


def _format_verdict_text(questions, answers) -> str:
    lines = ["VERDICT FORM"]
    for q in questions:
        qid = q.get("id", "")
        lines.append(f"{q.get('text', qid)} — {answers.get(qid, '(no answer returned)')}")
    return "\n".join(lines)


def run_session(
    judge_profile: Profile,
    counsel_a_profile: Profile,
    counsel_b_profile: Profile,
    case_description: str,
    case_type: str = "full_trial",
    num_rounds: int = 2,
    include_judge_questions: bool = True,
    run_id: str = None,
    outcome: dict = None,
):
    """Generator yielding one dict per transcript event as the simulated proceeding unfolds.

    Hard-branches on case_type:
      - "motion_hearing": no jury exists, so the judge decides the merits directly at the end —
        exactly as a real bench ruling on a motion would work. This is the ONLY path where the
        judge issues a merits ruling directly.
      - "full_trial": trial phase -> jury verdict (structured findings only, no jury opinion) ->
        post-trial motions -> post-verdict judge order (JMOL only if actually moved and only if
        the "no reasonable jury" standard is met; otherwise equitable relief / enhancement / fees
        / remittitur only — the jury's liability and willfulness findings are not revisited).

    If `outcome` (a dict) is passed in, it is populated with the structured, non-prose pieces of
    the result (verdict question/answers, whether JMOL was raised, etc.) so a caller — e.g. the
    batch variance endpoint — can aggregate across many runs without re-parsing transcript prose.
    """
    if outcome is None:
        outcome = {}
    run_id = run_id or uuid.uuid4().hex[:10]
    transcript_log = []

    def transcript_text():
        return "\n\n".join(f"[{e['phase']}] {e['speaker']}: {e['text']}" for e in transcript_log)

    def emit(phase, speaker, role, text, kind="statement"):
        entry = {"phase": phase, "speaker": speaker, "role": role, "text": text, "kind": kind}
        transcript_log.append(entry)
        return entry

    case_no = f"SIM-{uuid.uuid4().hex[:8].upper()}"
    yield emit(
        "intro",
        "Clerk",
        "system",
        f"Case No. {case_no} (run {run_id}) — {case_type.replace('_', ' ').title()}. {case_description}",
        kind="system",
    )

    counsel_a = PersonaAgent(counsel_a_profile, "Counsel for Party A", case_description, model=config.COUNSEL_MODEL)
    counsel_b = PersonaAgent(counsel_b_profile, "Counsel for Party B", case_description, model=config.COUNSEL_MODEL)
    judge = PersonaAgent(judge_profile, "Presiding Judge", case_description, model=config.JUDGE_MODEL)

    # --- Openings -----------------------------------------------------------------------------
    text = counsel_a.speak("Deliver your opening statement for this matter.", transcript_text())
    yield emit("opening", counsel_a.profile.name, "counsel_a", text)

    text = counsel_b.speak(
        "Deliver your opening statement, responding as appropriate to opposing counsel's opening.",
        transcript_text(),
    )
    yield emit("opening", counsel_b.profile.name, "counsel_b", text)

    # --- Argument rounds ------------------------------------------------------------------------
    # The judge's only role here is procedural: a clarifying question, or a brief procedural /
    # evidentiary note. It may never comment on who has the stronger case or preview a ruling —
    # that would smuggle a merits opinion into the trial phase, which is exactly what a jury (in
    # full_trial) or the eventual bench ruling (in motion_hearing) is supposed to decide instead.
    for i in range(num_rounds):
        rnum = i + 1
        text = counsel_a.speak(
            f"Present your round {rnum} argument, directly engaging with opposing counsel's most recent points.",
            transcript_text(),
        )
        yield emit(f"round_{rnum}", counsel_a.profile.name, "counsel_a", text)

        text = counsel_b.speak(
            f"Present your round {rnum} rebuttal, directly engaging with opposing counsel's most recent points.",
            transcript_text(),
        )
        yield emit(f"round_{rnum}", counsel_b.profile.name, "counsel_b", text)

        if include_judge_questions:
            action = judge.speak_json(
                "This is a procedural check-in only, not a ruling on the merits. Based on the "
                "argument so far this round, choose exactly ONE of: (1) ask one clarifying "
                "question of either party about their argument or the record; (2) issue a brief "
                "procedural or evidentiary note — for example flagging that an assertion is "
                "unsupported by the record, or a comment on the form or admissibility of an "
                "argument — without indicating who you think should ultimately win; or (3) do "
                "nothing. You must NOT state or imply an opinion on which side has the stronger "
                "case, how you (or a jury) will rule, or the ultimate outcome. Respond with ONLY "
                'JSON: {"action": "question"|"procedural_note"|"none", "target": "A"|"B", '
                '"question": "...", "note": "..."}. Leave irrelevant fields as empty strings.',
                transcript_text(),
            )
            act = (action.get("action") or "none").strip().lower()
            if act == "question":
                question_text = (action.get("question") or "").strip()
                if question_text:
                    yield emit(
                        f"round_{rnum}_question", judge.profile.name, "judge", question_text, kind="question"
                    )
                    target = counsel_b if action.get("target") == "B" else counsel_a
                    target_role = "counsel_b" if action.get("target") == "B" else "counsel_a"
                    answer = target.speak(
                        f'The judge has asked you: "{question_text}" Answer directly and concisely.',
                        transcript_text(),
                    )
                    yield emit(f"round_{rnum}_answer", target.profile.name, target_role, answer)
            elif act == "procedural_note":
                note_text = (action.get("note") or "").strip()
                if note_text:
                    yield emit(
                        f"round_{rnum}_note", judge.profile.name, "judge", note_text, kind="procedural"
                    )

    # --- Closings -------------------------------------------------------------------------------
    text = counsel_a.speak("Deliver your closing argument.", transcript_text())
    yield emit("closing", counsel_a.profile.name, "counsel_a", text)

    text = counsel_b.speak("Deliver your closing argument.", transcript_text())
    yield emit("closing", counsel_b.profile.name, "counsel_b", text)

    outcome["run_id"] = run_id
    outcome["case_type"] = case_type

    if case_type == "motion_hearing":
        # No jury exists for a motion hearing — the judge deciding the merits directly is correct
        # procedure here, not a shortcut. This is the one and only path that produces a merits
        # ruling straight from the bench.
        reasoning = judge.speak(
            "The argument has concluded. Privately deliberate: weigh each side's arguments against "
            "the case context, general applicable legal principles, and your documented tendencies "
            "where relevant. Write 2-4 paragraphs of internal reasoning only — this is not spoken "
            "in open court and a ruling statement will be requested separately, so do not state "
            "your final ruling yet, just your analysis.",
            transcript_text(),
            max_tokens=4096,
        )
        yield emit("deliberation", judge.profile.name, "judge", reasoning, kind="reasoning")

        ruling = judge.speak(
            "Based on the deliberation you just completed, now issue your ruling on this motion. "
            "There is no jury in a motion hearing, so you are the sole decision-maker here: state "
            "plainly whether the motion is granted, denied, or granted in part, and why. Write "
            "1-3 paragraphs stating your decision and its basis, in your voice as the presiding "
            "judge. This is a simulated predictive exercise, not an actual order of a court.",
            transcript_text(),
            max_tokens=4096,
        )
        yield emit("ruling", judge.profile.name, "judge", ruling, kind="ruling")
        outcome["ruling"] = ruling

    else:
        # --- Jury verdict stage (full_trial only) ------------------------------------------------
        # A separate generation step with a separate decision-maker. The judge prepares the verdict
        # form (as a real judge instructs the jury); the jury then answers ONLY those questions,
        # with no narrative reasoning — real verdict forms are findings, not opinions.
        form = judge.speak_json(
            "The evidence and argument phase has concluded. Prepare the SPECIAL VERDICT FORM you "
            "will give the jury. List only the specific factual questions the jury must answer to "
            "resolve the claims actually at issue in this case (for example, in a patent case: "
            "infringement yes/no per asserted claim, willfulness yes/no, and a damages amount — "
            "adapt this to whatever claims and case type are actually presented here). Do not "
            "include any question asking the jury to explain itself; verdict forms call for "
            'findings, not opinions. Respond with ONLY JSON: {"questions": [{"id": "q1", "text": '
            '"...", "type": "yes_no"|"amount"|"text_short"}, ...]}',
            transcript_text(),
        )
        questions = form.get("questions") or []
        if questions:
            form_text = "\n".join(f"- {q.get('text', q.get('id',''))}" for q in questions)
            yield emit(
                "jury_instructions", judge.profile.name, "judge",
                f"Members of the jury, you will answer the following on your verdict form:\n{form_text}",
                kind="instructions",
            )

        jury = JuryPanel(model=config.JURY_MODEL)
        answers = jury.deliberate(questions, transcript_text())
        verdict_text = _format_verdict_text(questions, answers)
        yield emit("jury_verdict", "Jury", "jury", verdict_text, kind="verdict")
        outcome["verdict_questions"] = questions
        outcome["verdict_answers"] = answers

        # --- Post-trial motions -------------------------------------------------------------------
        # Real JMOL practice, requests for injunctive relief/enhancement/fees, and remittitur
        # arguments are all raised as post-trial motions, not narrated by the judge unprompted.
        motion_instruction = (
            f"The jury has returned its verdict:\n{verdict_text}\n\n"
            "State any post-trial motions you wish to make now — for example: judgment as a "
            "matter of law (JMOL) on a specific finding, arguing no reasonable jury could have "
            "reached it on this record and why; a request for injunctive relief; a request to "
            "enhance the damages award based on a willfulness finding; a request for attorneys' "
            "fees; or a request for remittitur if you believe the damages figure is unsupported. "
            "If you have no post-trial motions, say so plainly in one sentence."
        )
        motion_a = counsel_a.speak(motion_instruction, transcript_text())
        yield emit("post_trial_motion", counsel_a.profile.name, "counsel_a", motion_a, kind="motion")

        motion_b = counsel_b.speak(motion_instruction, transcript_text())
        yield emit("post_trial_motion", counsel_b.profile.name, "counsel_b", motion_b, kind="motion")

        jmol_raised = _mentions_jmol(motion_a) or _mentions_jmol(motion_b)
        outcome["jmol_raised"] = jmol_raised

        # --- Post-verdict judge stage ---------------------------------------------------------
        # The verdict is a fixed input here, not something the judge can freely revise. The judge
        # may only set aside a specific jury finding if a party actually moved for JMOL on it AND
        # the "no reasonable jury" standard is met — this is enforced by telling the judge plainly
        # whether that motion was made at all, not left to the judge's own narration.
        if jmol_raised:
            jmol_clause = (
                "A party DID move for judgment as a matter of law above. You may address that "
                "motion, but you may only set aside the specific jury finding it targets if you "
                "conclude, applying the standard that no reasonable jury could have reached that "
                "finding on this record, that the standard is met — state explicitly whether it "
                "is met and why. Any finding not challenged by a JMOL motion, or challenged but "
                "not meeting this standard, stands exactly as the jury found it."
            )
        else:
            jmol_clause = (
                "No party moved for judgment as a matter of law. You have NO authority to revisit "
                "or overturn the jury's factual findings on liability, infringement, or "
                "willfulness in this order — treat them as final and binding, and address only "
                "the remaining post-verdict matters below."
            )

        order_instruction = f"""The jury's verdict (binding except as noted below) was:
{verdict_text}

Post-trial motions submitted:
— {counsel_a.profile.name} (Counsel for Party A): {motion_a}
— {counsel_b.profile.name} (Counsel for Party B): {motion_b}

{jmol_clause}

Within these constraints, issue your post-verdict order addressing what is actually raised or \
otherwise implicated by the verdict, and skip anything not applicable here:
1. Judgment as a matter of law, if properly raised (see above).
2. Equitable relief such as an injunction — apply the traditional four-factor test (irreparable \
harm, inadequacy of damages at law, balance of hardships, public interest) rather than presuming \
relief follows automatically from a liability finding. If this is a patent case this is the eBay \
v. MercExchange framework; apply the closest analogous doctrine if it is not a patent case.
3. If the jury found willfulness or comparable bad faith, whether to enhance the award in your \
discretion and by how much, and why. In a patent case this is 35 U.S.C. §284; use the closest \
analogous enhancement doctrine otherwise.
4. Whether fees are warranted and under what standard (in a patent case, 35 U.S.C. §285's \
exceptional-case standard; otherwise the closest analogous fee-shifting doctrine).
5. Remittitur, if the damages figure is unsupported by the record.

Write this as a judicial order in your own voice, with a short heading for each issue you \
actually address. This is a simulated predictive exercise, not an actual order of a court."""

        order = judge.speak(order_instruction, "", max_tokens=4096)
        yield emit("post_verdict_order", judge.profile.name, "judge", order, kind="order")
        outcome["post_verdict_order"] = order

    persist_run(run_id, {
        "case_no": case_no,
        "case_type": case_type,
        "case_description": case_description,
        "num_rounds": num_rounds,
        "judge": judge_profile.name,
        "counsel_a": counsel_a_profile.name,
        "counsel_b": counsel_b_profile.name,
        "transcript": transcript_log,
        "outcome": outcome,
    })


_MONEY_RE = re.compile(r"\$\s*([\d,]+(?:\.\d+)?)")


def _parse_amount(value) -> float:
    m = _MONEY_RE.search(str(value or ""))
    if not m:
        return 0.0
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return 0.0


def summarize_batch(outcomes: list) -> dict:
    """Aggregate the structured `outcome` dicts from several repeated runs of the same
    configuration into a spread report, so a single transcript is never mistaken for a settled
    signal. This only has real precision for the jury's structured verdict answers (yes_no /
    amount questions); anything about the post-verdict order's discretionary calls (injunction
    granted, fees awarded, etc.) is reported as a best-effort keyword count over the order text,
    not a verified structured field — read the raw per-run "results" alongside this summary rather
    than treating the heuristic counts as authoritative.
    """
    motion_outcomes = [o for o in outcomes if o.get("case_type") == "motion_hearing"]
    trial_outcomes = [o for o in outcomes if o.get("case_type") == "full_trial"]
    summary = {"num_runs": len(outcomes)}

    if motion_outcomes:
        granted = sum(1 for o in motion_outcomes if "grant" in (o.get("ruling") or "").lower()
                       and "denied" not in (o.get("ruling") or "").lower())
        summary["motion_hearing"] = {
            "runs": len(motion_outcomes),
            "granted_keyword_count": granted,
            "note": "Heuristic keyword count over ruling text ('grant' present, 'denied' absent) — read the rulings directly for anything that matters.",
        }

    if trial_outcomes:
        per_question = {}
        for o in trial_outcomes:
            for q in o.get("verdict_questions", []):
                qid, qtext, qtype = q.get("id"), q.get("text", ""), q.get("type", "text_short")
                per_question.setdefault(qid, {"text": qtext, "type": qtype, "answers": []})
                per_question[qid]["answers"].append(o.get("verdict_answers", {}).get(qid))

        question_summary = {}
        for qid, data in per_question.items():
            if data["type"] == "yes_no":
                yes = sum(1 for a in data["answers"] if str(a).strip().lower().startswith("y"))
                question_summary[qid] = {
                    "text": data["text"], "type": "yes_no",
                    "yes": yes, "no": len(data["answers"]) - yes, "answers": data["answers"],
                }
            elif data["type"] == "amount":
                amounts = [_parse_amount(a) for a in data["answers"]]
                question_summary[qid] = {
                    "text": data["text"], "type": "amount",
                    "min": min(amounts) if amounts else 0, "max": max(amounts) if amounts else 0,
                    "mean": sum(amounts) / len(amounts) if amounts else 0, "answers": data["answers"],
                }
            else:
                question_summary[qid] = {"text": data["text"], "type": data["type"], "answers": data["answers"]}

        jmol_count = sum(1 for o in trial_outcomes if o.get("jmol_raised"))
        summary["full_trial"] = {
            "runs": len(trial_outcomes),
            "verdict_questions": question_summary,
            "jmol_raised_count": jmol_count,
            "note": "Verdict question spreads are exact (structured jury output). Post-verdict order outcomes (injunction, fees, enhancement) are not aggregated here — read each run's post_verdict_order text directly.",
        }

    return summary
