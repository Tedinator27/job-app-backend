from fastapi import FastAPI, HTTPException, Depends, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from supabase import create_client, Client, ClientOptions
from anthropic import Anthropic
from pydantic import BaseModel
from typing import Optional
from mangum import Mangum
import os
import traceback
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

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "*",
    "Access-Control-Allow-Headers": "*",
}

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    traceback.print_exc()
    return JSONResponse(
        status_code=500,
        content={"detail": f"{type(exc).__name__}: {exc}"},
        headers=CORS_HEADERS,
    )

_client_opts = ClientOptions(auto_refresh_token=False, persist_session=False)


def get_supabase() -> Client:
    return create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_ANON_KEY"],
        options=_client_opts,
    )


def get_supabase_admin() -> Client:
    return create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_ROLE_KEY"],
        options=_client_opts,
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


class RefreshRequest(BaseModel):
    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    access_token: str
    new_password: str


async def current_user(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    try:
        supabase = get_supabase()
        user = supabase.auth.get_user(authorization.split(" ", 1)[1]).user
        if not user:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        return user
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


@app.get("/")
async def health():
    return {"status": "ok"}


@app.post("/auth/signup")
async def signup(req: AuthRequest):
    try:
        supabase = get_supabase()
        res = supabase.auth.sign_up({"email": req.email, "password": req.password})
        if not res.user:
            raise HTTPException(status_code=400, detail="Signup failed")
        token = res.session.access_token if res.session else None
        refresh = res.session.refresh_token if res.session else None
        return {"access_token": token, "refresh_token": refresh, "email": res.user.email}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/auth/login")
async def login(req: AuthRequest):
    try:
        supabase = get_supabase()
        res = supabase.auth.sign_in_with_password({"email": req.email, "password": req.password})
        return {
            "access_token": res.session.access_token,
            "refresh_token": res.session.refresh_token,
            "email": res.user.email,
        }
    except Exception:
        raise HTTPException(status_code=401, detail="Incorrect email or password.")


@app.post("/auth/refresh")
async def refresh_token(req: RefreshRequest):
    try:
        supabase = get_supabase()
        res = supabase.auth.refresh_session(req.refresh_token)
        return {
            "access_token": res.session.access_token,
            "refresh_token": res.session.refresh_token,
            "email": res.user.email,
        }
    except Exception:
        raise HTTPException(status_code=401, detail="Session expired. Please log in again.")


@app.post("/auth/forgot-password")
async def forgot_password(req: ForgotPasswordRequest):
    try:
        supabase = get_supabase()
        supabase.auth.reset_password_for_email(
            req.email,
            {"redirect_to": "https://job-app-assistant-psi.vercel.app/reset"},
        )
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/auth/reset-password")
async def reset_password(req: ResetPasswordRequest):
    try:
        supabase = get_supabase()
        supabase_admin = get_supabase_admin()
        user_res = supabase.auth.get_user(req.access_token)
        if not user_res.user:
            raise HTTPException(status_code=401, detail="Invalid or expired reset link.")
        supabase_admin.auth.admin.update_user_by_id(
            str(user_res.user.id),
            {"password": req.new_password},
        )
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/reset", response_class=HTMLResponse)
async def reset_page():
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>Reset Password - Job Apply Assistant</title>
  <style>
    *{box-sizing:border-box;margin:0;padding:0}
    body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f8fafc;display:flex;align-items:center;justify-content:center;min-height:100vh;padding:20px}
    .card{background:#fff;border-radius:12px;box-shadow:0 4px 24px rgba(0,0,0,.08);padding:36px 32px;width:100%;max-width:380px}
    h2{font-size:20px;font-weight:700;color:#0f172a;margin-bottom:6px}
    p{font-size:13.5px;color:#64748b;margin-bottom:20px}
    input{width:100%;padding:10px 12px;border:1px solid #e2e8f0;border-radius:8px;font-size:14px;margin-bottom:10px;outline:none;transition:border .15s}
    input:focus{border-color:#2563eb}
    button{width:100%;padding:11px;background:#2563eb;color:#fff;border:none;border-radius:8px;font-size:14px;font-weight:600;cursor:pointer;margin-top:4px}
    button:hover{background:#1d4ed8}
    button:disabled{background:#94a3b8;cursor:default}
    .msg{font-size:12.5px;margin-top:12px;padding:9px 11px;border-radius:6px;display:none}
    .msg.error{color:#dc2626;background:#fef2f2;border:1px solid #fecaca;display:block}
    .msg.success{color:#15803d;background:#f0fdf4;border:1px solid #86efac;display:block}
  </style>
</head>
<body>
<div class="card">
  <h2>Reset Your Password</h2>
  <p>Enter a new password for your account.</p>
  <input type="password" id="pw" placeholder="New password (min 8 characters)" minlength="8"/>
  <input type="password" id="pw2" placeholder="Confirm new password"/>
  <button id="btn" onclick="submit()">Set New Password</button>
  <div class="msg" id="msg"></div>
</div>
<script>
  const params=new URLSearchParams(location.hash.substring(1));
  const token=params.get('access_token');
  const type=params.get('type');
  if(!token||type!=='recovery'){
    document.querySelector('h2').textContent='Invalid or expired link';
    document.querySelector('p').textContent='This password reset link is no longer valid. Please request a new one.';
    document.getElementById('btn').disabled=true;
    document.getElementById('pw').style.display='none';
    document.getElementById('pw2').style.display='none';
  }
  async function submit(){
    const pw=document.getElementById('pw').value;
    const pw2=document.getElementById('pw2').value;
    const msg=document.getElementById('msg');
    msg.className='msg';msg.textContent='';
    if(pw.length<8){msg.className='msg error';msg.textContent='Password must be at least 8 characters.';return;}
    if(pw!==pw2){msg.className='msg error';msg.textContent='Passwords do not match.';return;}
    document.getElementById('btn').disabled=true;
    document.getElementById('btn').textContent='Saving...';
    try{
      const res=await fetch('/auth/reset-password',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({access_token:token,new_password:pw})});
      const data=await res.json();
      if(!res.ok)throw new Error(data.detail||'Something went wrong.');
      msg.className='msg success';msg.textContent='Password updated! You can now log in with your new password.';
      document.getElementById('btn').textContent='Done';
    }catch(e){
      msg.className='msg error';msg.textContent=e.message;
      document.getElementById('btn').disabled=false;
      document.getElementById('btn').textContent='Set New Password';
    }
  }
  document.addEventListener('keydown',e=>{if(e.key==='Enter')submit();});
</script>
</body>
</html>"""


@app.get("/profile")
async def get_profile(user=Depends(current_user)):
    supabase_admin = get_supabase_admin()
    res = supabase_admin.table("profiles").select("*").eq("user_id", str(user.id)).limit(1).execute()
    if not res.data:
        return {"resume": "", "linkedin": "", "github": ""}
    d = res.data[0]
    return {"resume": d.get("resume") or "", "linkedin": d.get("linkedin") or "", "github": d.get("github") or ""}


@app.put("/profile")
async def update_profile(body: ProfileUpdate, user=Depends(current_user)):
    supabase_admin = get_supabase_admin()
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    data["user_id"] = str(user.id)
    supabase_admin.table("profiles").upsert(data, on_conflict="user_id").execute()
    return {"ok": True}


@app.post("/generate")
async def generate(req: GenerateRequest, user=Depends(current_user)):
    supabase_admin = get_supabase_admin()
    try:
        msg = claude.messages.create(
            model=req.model,
            max_tokens=2048,
            system=req.system_prompt,
            messages=[{"role": "user", "content": req.user_prompt}],
        )
        output = msg.content[0].text
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

    try:
        supabase_admin.table("applications").insert({
            "user_id": str(user.id),
            "kind": req.kind,
            "company": req.company,
            "role": req.role,
            "output": output,
        }).execute()
    except Exception:
        pass

    return {"output": output}


@app.get("/history")
async def get_history(user=Depends(current_user)):
    supabase_admin = get_supabase_admin()
    try:
        res = (
            supabase_admin.table("applications")
            .select("id, kind, company, role, created_at")
            .eq("user_id", str(user.id))
            .order("created_at", desc=True)
            .limit(50)
            .execute()
        )
        return res.data or []
    except Exception:
        return []


@app.get("/history/{item_id}")
async def get_history_item(item_id: str, user=Depends(current_user)):
    supabase_admin = get_supabase_admin()
    try:
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
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=404, detail="Not found")


@app.delete("/history/{item_id}")
async def delete_history_item(item_id: str, user=Depends(current_user)):
    supabase_admin = get_supabase_admin()
    try:
        supabase_admin.table("applications").delete().eq("id", item_id).eq("user_id", str(user.id)).execute()
    except Exception:
        pass
    return {"ok": True}


handler = Mangum(app, lifespan="off")
