from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime


from schemas import BaziRequest, BaziResponse
from bazi import compute_bazi_local, InputArgs


app = FastAPI(title="Bazi API", version="1.0.0")


# Cho phép CORS
app.add_middleware(
CORSMiddleware,
allow_origins=["*"],
allow_credentials=True,
allow_methods=["*"],
allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/bazi", response_model=BaziResponse)
def api_bazi(req: BaziRequest):
    try:
        try:
            _dt = datetime.fromisoformat(req.dt)
        except Exception:
            raise HTTPException(status_code=400, detail="Tham số dt phải theo chuẩn ISO 8601. Ví dụ: 2002-10-06T05:30:00")


        args = InputArgs(
            dt=_dt,
            tz=req.tz,
            gender=req.gender,
            method=req.method,
            lon=req.lon,
            print_json=False,
            )
        data = compute_bazi_local(args)
        return BaziResponse(ok=True, data=data)
    except HTTPException:
        raise
    except Exception as e:
        return BaziResponse(ok=False, error=str(e))