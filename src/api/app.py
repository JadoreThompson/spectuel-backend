from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from api.exc import JWTError
from api.middlewares import RateLimitMiddleware
from api.routes.auth.router import router as auth_route
from api.routes.orders.router import route as orders_route
from api.routes.orders.service import OrderService, OrderServiceException
from api.routes.public.router import router as public_route
from api.routes.users.router import route as user_route
from api.ws.orders.route import router as ws_order_route
from api.ws.instruments.route import route as ws_instruments_route
from db_models import Instruments
from infra.db import get_db_sess


symbols = ("BTCUSD", "EURUSD", "GBPUSD", "FAKEUSD")


async def create_instruments():
    prices = (1.00, 5.00, 1.20, 0.75)
    try:
        async with get_db_sess() as db_sess:
            for symbol, price in zip(symbols, prices):
                db_sess.add(Instruments(symbol=symbol, starting_price=price))
            await db_sess.commit()
    except IntegrityError:
        pass


async def lifespan(app: FastAPI):
    await create_instruments()
    await OrderService.start()
    yield
    await OrderService.stop()


app = FastAPI(lifespan=lifespan)


app.include_router(auth_route)
app.include_router(orders_route)
app.include_router(public_route)
app.include_router(user_route)
app.include_router(ws_instruments_route)
app.include_router(ws_order_route)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)
app.add_middleware(RateLimitMiddleware)


@app.exception_handler(JWTError)
async def jwt_error_hanlder(req: Request, exc: JWTError):
    return JSONResponse(status_code=401, content={"error": str(exc)})


@app.exception_handler(OrderServiceException)
async def jwt_error_hanlder(req: Request, exc: OrderServiceException):
    return JSONResponse(status_code=401, content={"error": str(exc)})


@app.exception_handler(HTTPException)
async def http_exception_handler(req: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})


@app.exception_handler(RequestValidationError)
async def validation_error_handler(req: Request, exc: RequestValidationError):
    error_msg = str(exc.errors()[0]["ctx"]["error"])
    return JSONResponse(status_code=422, content={"error": error_msg})
