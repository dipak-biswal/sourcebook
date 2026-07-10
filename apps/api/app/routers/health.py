from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def helath():
    return {"status": "ok", "service": "sourcebook"}
