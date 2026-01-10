import uuid
from typing import Union

from sqlalchemy.ext.asyncio import AsyncSession

from api.routes.orders.models import (
    SingleOrderCreate,
    OCOOrderCreate,
    OTOOrderCreate,
    OTOCOOrderCreate,
    OrderBase,
)
from config import KAFKA_ENGINE_EVENTS_TOPIC
from db_models import Orders
from engine.commands import (
    NewOrderCommandBase,
    NewSingleOrderCommand,
    NewOCOOrderCommand,
    NewOTOOrderCommand,
    NewOTOCOOrderCommand,
    SingleOrderMeta,
)
from engine.enums import OrderStatus, StrategyType
from infra.kafka import AsyncKafkaProducer
from .exc import OrderServiceError


class OrderService:
    _producer: AsyncKafkaProducer | None = None
    _closed = True

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
    ) -> dict:
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
            raise OrderServiceError(
                f"Unsupported strategy type: {details.strategy_type}"
            )

    @classmethod
    async def _create_single(
        cls, user_id: uuid.UUID, details: SingleOrderCreate, db_sess: AsyncSession
    ) -> dict:
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
        )
        db_sess.add(db_order)
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

        await cls._send_command(command)

        return {"order_id": str(order_id), "status": "accepted"}

    @classmethod
    async def _create_oco(
        cls, user_id: uuid.UUID, details: OCOOrderCreate, db_sess: AsyncSession
    ) -> dict:
        group_id = uuid.uuid4()
        legs_meta = []
        leg_ids = []

        for leg_details in details.legs:
            leg_id = uuid.uuid4()
            leg_ids.append(str(leg_id))

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
                group_type=StrategyType.OCO,
            )
            db_sess.add(db_leg)

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

        command = NewOCOOrderCommand(
            symbol=details.symbol,
            strategy_type=StrategyType.OCO,
            legs=legs_meta,
        )

        await cls._send_command(command)

        return {"group_id": str(group_id), "legs": leg_ids}

    @classmethod
    async def _create_oto(
        cls, user_id: uuid.UUID, details: OTOOrderCreate, db_sess: AsyncSession
    ) -> dict:
        group_id = uuid.uuid4()

        parent_id = uuid.uuid4()
        db_parent = OrderService._build_db_order(
            user_id, details.symbol, details.parent, parent_id
        )
        db_parent.order_group_id = group_id
        db_sess.add(db_parent)

        child_id = uuid.uuid4()
        db_child = OrderService._build_db_order(
            user_id, details.symbol, details.child, child_id
        )
        db_child.order_group_id = group_id
        db_child.parent_order_id = parent_id
        db_sess.add(db_child)

        await db_sess.commit()

        command = NewOTOOrderCommand(
            symbol=details.symbol,
            strategy_type=StrategyType.OTO,
            parent=OrderService._to_meta(parent_id, user_id, details.parent),
            child=OrderService._to_meta(child_id, user_id, details.child),
        )

        await cls._send_command(command)

        return {
            "group_id": str(group_id),
            "parent_id": str(parent_id),
            "child_id": str(child_id),
        }

    @classmethod
    async def _create_otoco(
        cls, user_id: uuid.UUID, details: OTOCOOrderCreate, db_sess: AsyncSession
    ) -> dict:
        group_id = uuid.uuid4()
        symbol = details.parent.symbol

        parent_id = uuid.uuid4()
        db_parent = OrderService._build_db_order(user_id, details.parent, parent_id)
        db_parent.order_group_id = group_id
        db_sess.add(db_parent)

        child_ids = []
        legs_meta = []

        for leg_spec in details.oco_legs:
            leg_id = uuid.uuid4()
            child_ids.append(str(leg_id))

            db_leg = OrderService._build_db_order(user_id, symbol, leg_spec, leg_id)
            db_leg.order_group_id = group_id
            db_leg.parent_order_id = parent_id
            db_sess.add(db_leg)

            legs_meta.append(OrderService._to_meta(leg_id, user_id, leg_spec))

        await db_sess.commit()

        command = NewOTOCOOrderCommand(
            symbol=symbol,
            strategy_type=StrategyType.OTOCO,
            parent=OrderService._to_meta(parent_id, user_id, details.parent),
            oco_legs=legs_meta,
        )
        await cls._send_command(command)

        return {
            "group_id": str(group_id),
            "parent_id": str(parent_id),
            "legs": child_ids,
        }

    @classmethod
    def _build_db_order(
        cls, symbol: str, user_id: uuid.UUID, details: OrderBase, order_id: uuid.UUID
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

    @classmethod
    async def _send_command(cls, command: NewOrderCommandBase) -> None:
        await cls._producer.send(
            KAFKA_ENGINE_EVENTS_TOPIC,
            command.model_dump_json(),
            key=command.symbol.encode(),
        )
