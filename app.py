import json
from typing import Optional

from fastapi import FastAPI
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from models.profile import Profile, research_profile, save_profile
from models.courtroom import run_session

app = FastAPI(title="Legal Twin Simulation Lab")
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def index():
    return FileResponse("static/index.html")


class ResearchRequest(BaseModel):
    name: str
    role: str  # "judge" or "counsel"
    hint: Optional[str] = ""


@app.post("/api/profile/research")
def api_research_profile(req: ResearchRequest):
    try:
        profile = research_profile(req.name, req.role, req.hint or "")
        return profile.to_dict()
    except Exception as e:
        return Profile(
            name=req.name,
            role=req.role,
            found=False,
            confidence_note=f"Research call failed: {e}. Check that ANTHROPIC_API_KEY is set in .env "
            "and the server was restarted after adding it.",
        ).to_dict()


class SaveProfileRequest(BaseModel):
    profile: dict


@app.post("/api/profile/save")
def api_save_profile(req: SaveProfileRequest):
    profile = Profile.from_dict(req.profile)
    save_profile(profile)
    return profile.to_dict()


class StartSessionRequest(BaseModel):
    judge: dict
    counsel_a: dict
    counsel_b: dict
    case_description: str
    case_type: str = "full_trial"
    num_rounds: int = 2
    include_judge_questions: bool = True


@app.post("/api/session/start")
def api_start_session(req: StartSessionRequest):
    judge_profile = Profile.from_dict(req.judge)
    counsel_a_profile = Profile.from_dict(req.counsel_a)
    counsel_b_profile = Profile.from_dict(req.counsel_b)

    def event_stream():
        try:
            for entry in run_session(
                judge_profile,
                counsel_a_profile,
                counsel_b_profile,
                req.case_description,
                req.case_type,
                req.num_rounds,
                req.include_judge_questions,
            ):
                yield f"data: {json.dumps(entry)}\n\n"
            yield f"data: {json.dumps({'phase': 'done', 'speaker': '', 'role': 'system', 'text': '', 'kind': 'done'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'phase': 'error', 'speaker': 'System', 'role': 'system', 'text': str(e), 'kind': 'error'})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
