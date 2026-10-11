from pydantic import BaseModel, Field
from typing import Optional, Dict, Any


class BaziRequest(BaseModel):
    dt: str = Field(..., description="Thời gian ISO 8601, ví dụ: 2002-10-06T05:30:00")
    tz: str = Field("UTC+7", description="Múi giờ, ví dụ Asia/Ho_Chi_Minh hoặc UTC+7")
    gender: str = Field("M", description="M (Nam) hoặc F (Nữ)")
    method: str = Field("standard", description="standard | true_solar_time")
    lon: Optional[float] = Field(None, description="Kinh độ (dùng cho true_solar_time)")


class BaziResponse(BaseModel):
    ok: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None