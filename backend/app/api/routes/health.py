from fastapi import APIRouter, Request

from app.schemas.books import HealthResult


router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResult)
def health(request: Request) -> HealthResult:
    settings = request.app.state.settings
    return HealthResult(
        app=settings.app_name,
        environment=settings.app_env,
    )
