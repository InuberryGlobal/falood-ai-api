from fastapi import Depends, HTTPException
import jwt_service
from fastapi.security import OAuth2PasswordBearer

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="sign-in")

def current_user_id(token: str = Depends(oauth2_scheme)) -> str:
    payload = jwt_service.verify_token(token)
    user_id = payload.get("user_id") if payload else None
    if not user_id:
        raise HTTPException(status_code=403, detail="Invalid token")
    return str(user_id)
