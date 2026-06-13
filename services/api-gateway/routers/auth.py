import os
import datetime
import jwt
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

JWT_SECRET = os.getenv("JWT_SECRET", "super-secret-jwt-key")
JWT_ALGORITHM = "HS256"
CLIENT_API_KEY = os.getenv("CLIENT_API_KEY", "drone-secret")

class TokenRequest(BaseModel):
    client_id: str
    client_secret: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int

@router.post("/token", response_model=TokenResponse)
async def login_for_access_token(req: TokenRequest):
    if req.client_secret != CLIENT_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid client_secret")

    expires_delta = datetime.timedelta(hours=1)
    expire = datetime.datetime.utcnow() + expires_delta

    to_encode = {
        "sub": req.client_id,
        "exp": expire,
        "role": "drone_client"
    }

    encoded_jwt = jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)

    return TokenResponse(
        access_token=encoded_jwt,
        token_type="bearer",
        expires_in=int(expires_delta.total_seconds())
    )
