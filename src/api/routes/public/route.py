from fastapi import APIRouter


route = APIRouter(prefix="/public", tags=["Public"])


@route.get("/healthcheck")
async def healthcheck():
    return {"status": "healthy"}
