from fastapi import APIRouter

from src.schemas.requests import Login
from src.services.auth import sign_in

router = APIRouter(prefix="/auth")


@router.post("/login")
def login(body: Login):
    return sign_in(body.email, body.password)
