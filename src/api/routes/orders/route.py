from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from spectuel_engine_utils.enums import OrderStatus, Side
from spectuel_engine_utils.commands import (
    CommandType,
    CancelOrderCommand,
    ModifyOrderCommand,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import depends_jwt, depends_db_sess
from api.shared.models import PaginatedResponse
from api.typing import JWTPayload
from config import PAGE_SIZE
from db_models import Orders
from services import CommandBus
from .controller import cancel_all_orders as cancel_all_orders_controller
from .models import (
    OCOOrderCreate,
    OTOCOOrderCreate,
    OTOOrderCreate,
    OrderModify,
    OrderRead,
    SingleOrderCreate,
)
from .order_service import OrderService


route = APIRouter(prefix="/orders", tags=["orders"])
command_bus = CommandBus


@route.post("/", status_code=202)
async def create_order(
    details: SingleOrderCreate,
    jwt: JWTPayload = Depends(depends_jwt(False)),
    db_sess: AsyncSession = Depends(depends_db_sess),
):
    """
    Accepts a new single order.
    """
    try:
         return await OrderService.create(jwt.sub, details, db_sess)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@route.post("/oco", status_code=202)
async def create_oco_order(
    details: OCOOrderCreate,
    jwt: JWTPayload = Depends(depends_jwt()),
    db_sess: AsyncSession = Depends(depends_db_sess),
):
    """
    Accepts a new OCO (One-Cancels-the-Other) order group.
    """
    try:
        return await OrderService.create(jwt.sub, details, db_sess)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@route.post("/oto", status_code=202)
async def create_oto_order(
    details: OTOOrderCreate,
    jwt: JWTPayload = Depends(depends_jwt()),
    db_sess: AsyncSession = Depends(depends_db_sess),
):
    """
    Accepts a new OTO (One-Triggers-the-Other) order group.
    """
    try:
        return await OrderService.create(jwt.sub, details, db_sess)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@route.post("/otoco", status_code=202)
async def create_otoco_order(
    details: OTOCOOrderCreate,
    jwt: JWTPayload = Depends(depends_jwt()),
    db_sess: AsyncSession = Depends(depends_db_sess),
):
    """
    Accepts a new OTOCO (One-Triggers-One-Cancels-the-Other) order group.
    """
    try:
        return await OrderService.create(jwt.sub, details, db_sess)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@route.get("/", response_model=PaginatedResponse[OrderRead])
async def get_orders(
    page: int = Query(1, ge=1),
    instrument: list[str] = Query(default_factory=list),
    status: list[OrderStatus] = Query(default_factory=list),
    side: list[Side] = Query(default_factory=list),
    jwt: JWTPayload = Depends(depends_jwt()),
    db_sess: AsyncSession = Depends(depends_db_sess),
):
    """
    Retrieves a paginated list of orders for the authenticated user,
    with optional filtering.
    """
    query = select(Orders).where(Orders.user_id == jwt.sub)

    if instrument:
        query = query.where(Orders.instrument_id.in_(instrument))
    if status:
        query = query.where(Orders.status.in_([s.value for s in status]))
    if side:
        query = query.where(Orders.side.in_([s.value for s in side]))

    offset = (page - 1) * PAGE_SIZE
    query = query.order_by(Orders.created_at.desc()).offset(offset).limit(PAGE_SIZE + 1)

    result = await db_sess.execute(query)
    orders = result.scalars().all()

    has_next = len(orders) > PAGE_SIZE

    return PaginatedResponse[OrderRead](
        page=page,
        size=len(orders[:PAGE_SIZE]),
        has_next=has_next,
        data=[OrderRead(**vars(o)) for o in orders[:PAGE_SIZE]],
    )


@route.get("/{order_id}", response_model=OrderRead)
async def get_order(
    order_id: UUID,
    jwt: JWTPayload = Depends(depends_jwt()),
    db_sess: AsyncSession = Depends(depends_db_sess),
):
    """Retrieves a single order by its ID."""
    order = await db_sess.get(Orders, order_id)
    if not order or order.user_id != jwt.sub:
        raise HTTPException(status_code=404, detail="Order not found")

    dumped = vars(order)
    if "_sa_instance_state" in dumped:
        dumped.pop("_sa_instance_state")
    return OrderRead(**dumped)


@route.patch("/{order_id}", status_code=202, summary="Modify an active order")
async def modify_order(
    order_id: UUID,
    details: OrderModify,
    jwt: JWTPayload = Depends(depends_jwt()),
    db_sess: AsyncSession = Depends(depends_db_sess),
):
    """Requests modification of an active order (e.g., changing the price)."""
    order = await db_sess.scalar(
        select(Orders).where(Orders.order_id == order_id, Orders.user_id == jwt.sub)
    )
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.status == OrderStatus.FILLED:
        raise HTTPException(
            status_code=400, detail="Cannot perform operation on filled order"
        )

    command = ModifyOrderCommand(
        version=1,
        order_id=order_id,
        limit_price=details.limit_price,
        stop_price=details.stop_price,
    )
    await command_bus.put(command)


@route.delete("/{order_id}", status_code=202, summary="Cancel a specific order")
async def cancel_order(
    order_id: UUID,
    jwt: JWTPayload = Depends(depends_jwt()),
    db_sess: AsyncSession = Depends(depends_db_sess),
):
    """Sends a request to cancel a specific order by its ID."""
    res = await db_sess.execute(
        select(Orders).where(Orders.order_id == order_id, Orders.user_id == jwt.sub)
    )
    order = res.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    cmd_data = CancelOrderCommand(
        version=1,
        type=CommandType.CANCEL_ORDER,
        order_id=str(order_id),
        instrument_id=order.instrument_id,
    )

    await command_bus.put(cmd_data)


@route.delete(
    "/symbol", status_code=202, summary="Cancel all active orders for the user"
)
async def cancel_all_orders(
    symbol: str | None,
    jwt: JWTPayload = Depends(depends_jwt()),
    db_sess: AsyncSession = Depends(depends_db_sess),
):
    """Sends requests to cancel all PENDING or PARTIALLY_FILLED orders."""
    await cancel_all_orders_controller(jwt.sub, db_sess)
