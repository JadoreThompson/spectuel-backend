from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from api.exc import JWTError
from api.middlewares import RateLimitMiddleware
from api.routers.auth.router import router as auth_route
from api.routers.orders.router import route as orders_route
from api.routers.orders.service import OrderService, OrderServiceException
from api.routers.public.router import router as public_route
from api.routers.users.router import route as user_route
from api.routers.markets.router import route as markets_route
from api.routers.markets.connection_manager import connection_manager
from api.ws.orders.route import router as ws_order_route
from api.ws.instruments.route import route as ws_instruments_route
from db_models import Instruments
from infra.db import get_db_sess
from services.ohlc_builder import OHLCBuilder


symbols = ("BTCUSD", "EURUSD", "GBPUSD", "FAKEUSD")

ohlc_builder = OHLCBuilder()


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
    await connection_manager.start()
    await ohlc_builder.start()
    yield
    await OrderService.stop()
    await connection_manager.stop()
    await ohlc_builder.stop()


app = FastAPI(lifespan=lifespan)


app.include_router(auth_route)
app.include_router(orders_route)
app.include_router(public_route)
app.include_router(user_route)
app.include_router(markets_route)
app.include_router(ws_instruments_route)
app.include_router(ws_order_route)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)
# app.add_middleware(RateLimitMiddleware)


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
    error: dict = exc.errors()[0]
    
    if msg := error.get("ctx", {}).get("error"):
        error_msg = str(msg)
    elif msg := error.get("msg"):
        error_msg = msg
    else:
        error_msg = 'Invalid request payload'
    
    return JSONResponse(status_code=422, content={"error": error_msg})
