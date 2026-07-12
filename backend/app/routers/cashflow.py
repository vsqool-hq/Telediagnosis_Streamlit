"""Router modułu CASHFLOW — jeden endpoint zwracający całą prognozę (kubełki
tygodniowe + kafelki KPI), liczony na żądanie (jak Pulpit). Zob. app.engine.cashflow.
"""

from fastapi import APIRouter

from app.engine import cashflow as cf

router = APIRouter(prefix="/api/cashflow", tags=["cashflow"])


@router.get("/overview")
async def overview():
    return cf.build_cashflow()
