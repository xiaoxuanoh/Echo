import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.api.routes import books, health
from app.core.config import Settings, get_settings
from app.core.errors import EchoError
from app.services.book_processing import LocalBookJobRegistry


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or get_settings()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    application = FastAPI(title=active_settings.app_name)
    application.state.settings = active_settings
    application.state.book_job_registry = LocalBookJobRegistry()
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[active_settings.frontend_origin],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type"],
    )

    @application.exception_handler(EchoError)
    async def echo_error_handler(_: Request, error: EchoError) -> JSONResponse:
        return JSONResponse(
            status_code=error.status_code,
            content={
                "error": {
                    "code": error.code,
                    "message": error.message,
                    "details": error.details,
                }
            },
        )

    @application.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _: Request, error: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "invalid_request",
                    "message": "The upload request is incomplete or invalid.",
                    "details": {"fields": jsonable_encoder(error.errors())},
                }
            },
        )

    application.include_router(health.router)
    application.include_router(books.router)
    return application


app = create_app()
