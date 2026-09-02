import uuid

import config
from .agent import PersonaAgent
from .profile import Profile


def run_session(
    judge_profile: Profile,
    counsel_a_profile: Profile,
    counsel_b_profile: Profile,
    case_description: str,
    case_type: str = "full_trial",
    num_rounds: int = 2,
    include_judge_questions: bool = True,
):
    """Generator yielding one dict per transcript event as the simulated proceeding unfolds."""
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
        f"Case No. {case_no} — {case_type.replace('_', ' ').title()}. {case_description}",
        kind="system",
    )

    counsel_a = PersonaAgent(counsel_a_profile, "Counsel for Party A", case_description, model=config.COUNSEL_MODEL)
    counsel_b = PersonaAgent(counsel_b_profile, "Counsel for Party B", case_description, model=config.COUNSEL_MODEL)
    judge = PersonaAgent(judge_profile, "Presiding Judge", case_description, model=config.JUDGE_MODEL)

    text = counsel_a.speak("Deliver your opening statement for this matter.", transcript_text())
    yield emit("opening", counsel_a.profile.name, "counsel_a", text)

    text = counsel_b.speak(
        "Deliver your opening statement, responding as appropriate to opposing counsel's opening.",
        transcript_text(),
    )
    yield emit("opening", counsel_b.profile.name, "counsel_b", text)

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
            q = judge.speak_json(
                "Decide whether you have ONE clarifying question for either party based on the "
                "argument so far this round. Respond with JSON: "
                '{"has_question": true or false, "target": "A" or "B", "question": "..."}. '
                "If you have no question, set has_question to false and question to an empty string.",
                transcript_text(),
            )
            if q.get("has_question"):
                question_text = (q.get("question") or "").strip()
                if question_text:
                    yield emit(
                        f"round_{rnum}_question", judge.profile.name, "judge", question_text, kind="question"
                    )
                    target = counsel_b if q.get("target") == "B" else counsel_a
                    target_role = "counsel_b" if q.get("target") == "B" else "counsel_a"
                    answer = target.speak(
                        f'The judge has asked you: "{question_text}" Answer directly and concisely.',
                        transcript_text(),
                    )
                    yield emit(f"round_{rnum}_answer", target.profile.name, target_role, answer)

    text = counsel_a.speak("Deliver your closing argument.", transcript_text())
    yield emit("closing", counsel_a.profile.name, "counsel_a", text)

    text = counsel_b.speak("Deliver your closing argument.", transcript_text())
    yield emit("closing", counsel_b.profile.name, "counsel_b", text)

    reasoning = judge.speak(
        "The proceeding has concluded. Privately deliberate: weigh each side's arguments against "
        "the case context, general applicable legal principles, and your documented tendencies "
        "where relevant. Write 2-4 paragraphs of internal reasoning only — this is not spoken in "
        "open court and a ruling statement will be requested separately, so do not state your final "
        "ruling yet, just your analysis.",
        transcript_text(),
        max_tokens=4096,
    )
    yield emit("deliberation", judge.profile.name, "judge", reasoning, kind="reasoning")

    # ruling = judge.speak(
    #     "Based on the deliberation you just completed, now issue your ruling. Write 1-3 paragraphs "
    #     "stating your decision and its basis, in your voice as the presiding judge. This is a "
    #     "simulated predictive exercise, not an actual order of a court.",
    #     transcript_text(),
    #     max_tokens=4096,
    # )
    ruling = judge.speak(
        "Based on the deliberation you just completed, now issue your ruling. This simulation has "
        "no jury, so you must personally resolve the case as the final fact-finder: state plainly "
        "which party prevails on each claim or issue in dispute, and what relief (if any) is "
        "awarded. Do not defer the ultimate outcome to a jury or to a future proceeding — reach a "
        "conclusion now. Write 1-3 paragraphs stating your decision and its basis, in your voice as "
        "the presiding judge. This is a simulated predictive exercise, not an actual order of a court.",
        transcript_text(),
        max_tokens=4096,
    )
    yield emit("ruling", judge.profile.name, "judge", ruling, kind="ruling")
