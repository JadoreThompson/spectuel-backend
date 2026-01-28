import uuid
from typing import Union

from sqlalchemy.ext.asyncio import AsyncSession

from api.routers.orders.models import (
    SingleOrderCreate,
    OCOOrderCreate,
    OTOOrderCreate,
    OTOCOOrderCreate,
    OrderBase,
    SingleOrderResponse,
    OCOOrderResponse,
    OTOOrderResponse,
    OTOCOOrderResponse,
    OrderRead,
)
from api.utils import put_command
from db_models import Orders
from engine.commands import (
    NewSingleOrderCommand,
    NewOCOOrderCommand,
    NewOTOOrderCommand,
    NewOTOCOOrderCommand,
    SingleOrderMeta,
)
from engine.enums import OrderStatus, StrategyType
from infra.kafka import AsyncKafkaProducer
from .exc import OrderServiceException


class OrderService:
    _producer: AsyncKafkaProducer | None = None
    _closed = False

    @classmethod
    async def start(cls):
        cls._producer = AsyncKafkaProducer()
        await cls._producer.start()

    @classmethod
    async def stop(cls):
        if cls._closed:
            return

        cls._closed = True
        await cls._producer.stop()

    @classmethod
    async def create(
        cls,
        user_id: str | uuid.UUID,
        details: Union[
            SingleOrderCreate, OCOOrderCreate, OTOOrderCreate, OTOCOOrderCreate
        ],
        db_sess: AsyncSession,
    ) -> Union[SingleOrderResponse, OCOOrderResponse, OTOOrderResponse, OTOCOOrderResponse]:
        """
        Main entry point for order creation. Dispatches to specific handlers based on strategy type.
        """
        user_id = uuid.UUID(str(user_id))

        if details.strategy_type == StrategyType.SINGLE:
            return await cls._create_single(user_id, details, db_sess)
        elif details.strategy_type == StrategyType.OCO:
            return await cls._create_oco(user_id, details, db_sess)
        elif details.strategy_type == StrategyType.OTO:
            return await cls._create_oto(user_id, details, db_sess)
        elif details.strategy_type == StrategyType.OTOCO:
            return await cls._create_otoco(user_id, details, db_sess)
        else:
            raise OrderServiceException(
                f"Unsupported strategy type: {details.strategy_type}"
            )

    @classmethod
    async def _create_single(
        cls, user_id: uuid.UUID, details: SingleOrderCreate, db_sess: AsyncSession
    ) -> SingleOrderResponse:
        order_id = uuid.uuid4()
        db_order = Orders(
            order_id=order_id,
            user_id=user_id,
            symbol=details.symbol,
            side=details.side.value,
            order_type=details.order_type.value,
            quantity=details.quantity,
            limit_price=details.limit_price,
            stop_price=details.stop_price,
            status=OrderStatus.PENDING.value,
            strategy_type=StrategyType.SINGLE,
        )
        db_sess.add(db_order)
        # await db_sess.refresh(db_order)
        await db_sess.commit()

        meta = SingleOrderMeta(
            order_id=order_id,
            user_id=user_id,
            order_type=details.order_type,
            side=details.side,
            quantity=details.quantity,
            limit_price=details.limit_price,
            stop_price=details.stop_price,
        )

        command = NewSingleOrderCommand(
            symbol=details.symbol,
            strategy_type=StrategyType.SINGLE,
            **meta.model_dump(),
        )

        await put_command(command, details.symbol)

        return SingleOrderResponse(
            order=OrderRead(
                order_id=db_order.order_id,
                symbol=db_order.symbol,
                strategy_type=db_order.strategy_type,
                order_type=db_order.order_type,
                side=db_order.side,
                quantity=db_order.quantity,
                limit_price=db_order.limit_price,
                stop_price=db_order.stop_price,
                status=db_order.status,
                executed_quantity=db_order.executed_quantity,
                avg_fill_price=db_order.avg_fill_price,
                created_at=db_order.created_at,
            )
        )

    @classmethod
    async def _create_oco(
        cls, user_id: uuid.UUID, details: OCOOrderCreate, db_sess: AsyncSession
    ) -> OCOOrderResponse:
        group_id = uuid.uuid4()
        legs_meta = []
        db_legs = []

        for leg_details in details.legs:
            leg_id = uuid.uuid4()

            db_leg = Orders(
                order_id=leg_id,
                user_id=user_id,
                order_group_id=group_id,
                symbol=details.symbol,
                side=leg_details.side.value,
                order_type=leg_details.order_type.value,
                quantity=leg_details.quantity,
                limit_price=leg_details.limit_price,
                stop_price=leg_details.stop_price,
                status=OrderStatus.PENDING.value,
                strategy_type=StrategyType.OCO,
            )
            db_sess.add(db_leg)
            db_legs.append(db_leg)

            legs_meta.append(
                SingleOrderMeta(
                    order_id=leg_id,
                    user_id=user_id,
                    order_type=leg_details.order_type,
                    side=leg_details.side,
                    quantity=leg_details.quantity,
                    limit_price=leg_details.limit_price,
                    stop_price=leg_details.stop_price,
                )
            )

        await db_sess.commit()
        for db_leg in db_legs:
            await db_sess.refresh(db_leg)

        command = NewOCOOrderCommand(
            symbol=details.symbol,
            strategy_type=StrategyType.OCO,
            legs=legs_meta,
        )

        await put_command(command, details.symbol)

        return OCOOrderResponse(
            group_id=group_id,
            legs=[
                OrderRead(
                    order_id=leg.order_id,
                    symbol=leg.symbol,
                    strategy_type=leg.strategy_type,
                    order_type=leg.order_type,
                    side=leg.side,
                    quantity=leg.quantity,
                    limit_price=leg.limit_price,
                    stop_price=leg.stop_price,
                    status=leg.status,
                    executed_quantity=leg.executed_quantity,
                    avg_fill_price=leg.avg_fill_price,
                    created_at=leg.created_at,
                )
                for leg in db_legs
            ],
        )

    @classmethod
    async def _create_oto(
        cls, user_id: uuid.UUID, details: OTOOrderCreate, db_sess: AsyncSession
    ) -> OTOOrderResponse:
        group_id = uuid.uuid4()

        parent_id = uuid.uuid4()
        db_parent = cls._build_db_order(
            details.symbol, user_id, details.parent, parent_id, StrategyType.OTO
        )
        db_parent.order_group_id = group_id
        db_sess.add(db_parent)

        child_id = uuid.uuid4()
        db_child = cls._build_db_order(details.symbol, user_id, details.child, child_id, StrategyType.OTO)
        db_child.order_group_id = group_id
        db_child.parent_order_id = parent_id
        db_sess.add(db_child)

        await db_sess.commit()
        await db_sess.refresh(db_parent)
        await db_sess.refresh(db_child)

        command = NewOTOOrderCommand(
            symbol=details.symbol,
            strategy_type=StrategyType.OTO,
            parent=cls._to_meta(parent_id, user_id, details.parent),
            child=cls._to_meta(child_id, user_id, details.child),
        )

        await put_command(command, details.symbol)

        return OTOOrderResponse(
            parent=OrderRead(
                order_id=db_parent.order_id,
                symbol=db_parent.symbol,
                strategy_type=db_parent.strategy_type,
                order_type=db_parent.order_type,
                side=db_parent.side,
                quantity=db_parent.quantity,
                limit_price=db_parent.limit_price,
                stop_price=db_parent.stop_price,
                status=db_parent.status,
                executed_quantity=db_parent.executed_quantity,
                avg_fill_price=db_parent.avg_fill_price,
                created_at=db_parent.created_at,
            ),
            child=OrderRead(
                order_id=db_child.order_id,
                symbol=db_child.symbol,
                strategy_type=db_child.strategy_type,
                order_type=db_child.order_type,
                side=db_child.side,
                quantity=db_child.quantity,
                limit_price=db_child.limit_price,
                stop_price=db_child.stop_price,
                status=db_child.status,
                executed_quantity=db_child.executed_quantity,
                avg_fill_price=db_child.avg_fill_price,
                created_at=db_child.created_at,
            ),
        )

    @classmethod
    async def _create_otoco(
        cls, user_id: uuid.UUID, details: OTOCOOrderCreate, db_sess: AsyncSession
    ) -> OTOCOOrderResponse:
        group_id = uuid.uuid4()
        symbol = details.symbol

        parent_id = uuid.uuid4()
        db_parent = cls._build_db_order(symbol, user_id, details.parent, parent_id, StrategyType.OTOCO)
        db_parent.order_group_id = group_id
        db_sess.add(db_parent)

        db_legs = []
        legs_meta = []

        for leg_spec in details.oco_legs:
            leg_id = uuid.uuid4()

            db_leg = cls._build_db_order(symbol, user_id, leg_spec, leg_id, StrategyType.OTOCO)
            db_leg.order_group_id = group_id
            db_leg.parent_order_id = parent_id
            db_sess.add(db_leg)
            db_legs.append(db_leg)

            legs_meta.append(OrderService._to_meta(leg_id, user_id, leg_spec))

        await db_sess.commit()
        await db_sess.refresh(db_parent)
        for db_leg in db_legs:
            await db_sess.refresh(db_leg)

        command = NewOTOCOOrderCommand(
            symbol=symbol,
            strategy_type=StrategyType.OTOCO,
            parent=cls._to_meta(parent_id, user_id, details.parent),
            oco_legs=legs_meta,
        )
        await put_command(command, symbol)

        return OTOCOOrderResponse(
            group_id=group_id,
            parent=OrderRead(
                order_id=db_parent.order_id,
                symbol=db_parent.symbol,
                strategy_type=db_parent.strategy_type,
                order_type=db_parent.order_type,
                side=db_parent.side,
                quantity=db_parent.quantity,
                limit_price=db_parent.limit_price,
                stop_price=db_parent.stop_price,
                status=db_parent.status,
                executed_quantity=db_parent.executed_quantity,
                avg_fill_price=db_parent.avg_fill_price,
                created_at=db_parent.created_at,
            ),
            legs=[
                OrderRead(
                    order_id=leg.order_id,
                    symbol=leg.symbol,
                    strategy_type=leg.strategy_type,
                    order_type=leg.order_type,
                    side=leg.side,
                    quantity=leg.quantity,
                    limit_price=leg.limit_price,
                    stop_price=leg.stop_price,
                    status=leg.status,
                    executed_quantity=leg.executed_quantity,
                    avg_fill_price=leg.avg_fill_price,
                    created_at=leg.created_at,
                )
                for leg in db_legs
            ],
        )

    @classmethod
    def _build_db_order(
        cls, symbol: str, user_id: uuid.UUID, details: OrderBase, order_id: uuid.UUID, strategy_type: StrategyType
    ) -> Orders:
        """Helper to map API model to DB model."""
        return Orders(
            order_id=order_id,
            user_id=user_id,
            symbol=symbol,
            side=details.side.value,
            order_type=details.order_type.value,
            quantity=details.quantity,
            limit_price=details.limit_price,
            stop_price=details.stop_price,
            status=OrderStatus.PENDING.value,
            strategy_type=strategy_type
        )

    @classmethod
    def _to_meta(
        cls, order_id: uuid.UUID, user_id: uuid.UUID, details: OrderBase
    ) -> SingleOrderMeta:
        """Helper to map API model to Engine Command Meta."""
        return SingleOrderMeta(
            order_id=order_id,
            user_id=user_id,
            order_type=details.order_type,
            side=details.side,
            quantity=details.quantity,
            limit_price=details.limit_price,
            stop_price=details.stop_price,
        )
