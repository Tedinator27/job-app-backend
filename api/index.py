from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client, Client
from anthropic import Anthropic
from pydantic import BaseModel
from typing import Optional
from mangum import Mangum
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

supabase: Client = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_ANON_KEY"],
)
supabase_admin: Client = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_SERVICE_KEY"],
)
claude = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


class AuthRequest(BaseModel):
    email: str
    password: str


class GenerateRequest(BaseModel):
    kind: str  # coverLetter | resume | questions
    system_prompt: str
    user_prompt: str
    model: str
    company: Optional[str] = None
    role: Optional[str] = None


class ProfileUpdate(BaseModel):
    resume: Optional[str] = None
    linkedin: Optional[str] = None
    github: Optional[str] = None


async def current_user(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    try:
        return supabase.auth.get_user(authorization.split(" ", 1)[1]).user
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


@app.get("/")
async def health():
    return {"status": "ok"}


@app.post("/auth/signup")
async def signup(req: AuthRequest):
    try:
        res = supabase.auth.sign_up({"email": req.email, "password": req.password})
        if not res.user:
            raise HTTPException(status_code=400, detail="Signup failed")
        token = res.session.access_token if res.session else None
        return {"access_token": token, "email": res.user.email}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/auth/login")
async def login(req: AuthRequest):
    try:
        res = supabase.auth.sign_in_with_password({"email": req.email, "password": req.password})
        return {"access_token": res.session.access_token, "email": res.user.email}
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid email or password")


@app.get("/profile")
async def get_profile(user=Depends(current_user)):
    res = supabase_admin.table("profiles").select("*").eq("user_id", str(user.id)).limit(1).execute()
    if not res.data:
        return {"resume": "", "linkedin": "", "github": ""}
    d = res.data[0]
    return {"resume": d.get("resume") or "", "linkedin": d.get("linkedin") or "", "github": d.get("github") or ""}


@app.put("/profile")
async def update_profile(body: ProfileUpdate, user=Depends(current_user)):
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    data["user_id"] = str(user.id)
    supabase_admin.table("profiles").upsert(data, on_conflict="user_id").execute()
    return {"ok": True}


@app.post("/generate")
async def generate(req: GenerateRequest, user=Depends(current_user)):
    try:
        msg = claude.messages.create(
            model=req.model,
            max_tokens=2048,
            system=req.system_prompt,
            messages=[{"role": "user", "content": req.user_prompt}],
        )
        output = msg.content[0].text
        supabase_admin.table("applications").insert({
            "user_id": str(user.id),
            "kind": req.kind,
            "company": req.company,
            "role": req.role,
            "output": output,
        }).execute()
        return {"output": output}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/history")
async def get_history(user=Depends(current_user)):
    res = (
        supabase_admin.table("applications")
        .select("id, kind, company, role, created_at")
        .eq("user_id", str(user.id))
        .order("created_at", desc=True)
        .limit(50)
        .execute()
    )
    return res.data or []


@app.get("/history/{item_id}")
async def get_history_item(item_id: str, user=Depends(current_user)):
    res = (
        supabase_admin.table("applications")
        .select("*")
        .eq("id", item_id)
        .eq("user_id", str(user.id))
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="Not found")
    return res.data[0]


@app.delete("/history/{item_id}")
async def delete_history_item(item_id: str, user=Depends(current_user)):
    supabase_admin.table("applications").delete().eq("id", item_id).eq("user_id", str(user.id)).execute()
    return {"ok": True}


handler = Mangum(app, lifespan="off")
