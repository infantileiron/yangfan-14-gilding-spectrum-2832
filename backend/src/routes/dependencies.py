from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.constants.workflow import Role
from src.services.auth import validate

bearer = HTTPBearer(auto_error=False)


def current_account(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
    if credentials is None:
        raise HTTPException(401, "请先登录。")
    return validate(credentials.credentials)


def analyst(account=Depends(current_account)):
    if account.role != Role.ANALYST.value:
        raise HTTPException(403, "仅分析员可以导入数据并提交计算。")
    return account


def reviewer(account=Depends(current_account)):
    if account.role != Role.REVIEWER.value:
        raise HTTPException(403, "仅复核员可以签审交接。")
    return account
