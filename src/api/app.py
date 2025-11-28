from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.exc import JWTError
from api.routes.auth.route import route as auth_route
from api.routes.instruments.route import route as instruments_route
from api.routes.orders.route import route as orders_route
from api.routes.public.route import route as public_route
from api.routes.users.route import route as user_route
from .websockets.route import route as ws_route


app = FastAPI()


app.include_router(auth_route)
app.include_router(instruments_route)
app.include_router(orders_route)
app.include_router(public_route)
app.include_router(user_route)
app.include_router(ws_route)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)


@app.exception_handler(JWTError)
async def jwt_error_hanlder(req: Request, exc: JWTError):
    return JSONResponse(status_code=403, content={"error": str(exc)})
