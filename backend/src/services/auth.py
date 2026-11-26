from datetime import datetime, timedelta, timezone

import jwt
from fastapi import HTTPException

from src.config.settings import JWT_ISSUER, JWT_SECRET, Session
from src.models.account import Account
from src.utils.passwords import verify_password


def sign_in(email, password):
    with Session() as db:
        account = db.get(Account, email.lower())
    if not account or not verify_password(password, account.password_hash):
        raise HTTPException(401, "账号或密码无效。")
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {"sub": account.email, "iss": JWT_ISSUER, "iat": now, "exp": now + timedelta(hours=4)},
        JWT_SECRET,
        algorithm="HS256",
    )
    return {"token": token, "email": account.email, "role": account.role}


def validate(token):
    try:
        claims = jwt.decode(token, JWT_SECRET, algorithms=["HS256"], issuer=JWT_ISSUER, options={"require": ["exp", "sub"]})
    except jwt.InvalidTokenError as exc:
        raise HTTPException(401, "会话已失效，请重新登录。") from exc
    with Session() as db:
        account = db.get(Account, claims["sub"])
    if account is None:
        raise HTTPException(401, "账号已失效。")
    return account
