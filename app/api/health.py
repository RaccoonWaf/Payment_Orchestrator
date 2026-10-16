from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get(
        "/health",
        summary="chek health apps"
        )
async def health():
    return {"status": "ok"}
