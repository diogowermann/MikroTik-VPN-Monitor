from fastapi import APIRouter

router = APIRouter(tags=["operational"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "contract": "v1"}
