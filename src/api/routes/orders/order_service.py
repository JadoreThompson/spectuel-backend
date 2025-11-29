import uuid
from typing import Union
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from spectuel_engine_utils.commands import (
    NewSingleOrderCommand,
    NewOCOOrderCommand,
    NewOTOOrderCommand,
    NewOTOCOOrderCommand,
    SingleOrderMeta,
)
from spectuel_engine_utils.enums import OrderStatus, StrategyType

from db_models import Orders
from services import CommandBus
from .models import (
    SingleOrderCreate,
    OCOOrderCreate,
    OTOOrderCreate,
    OTOCOOrderCreate,
    OrderBase,
)


class OrderService:
    @staticmethod
    async def create(
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

        bus = CommandBus()

        if details.strategy_type == StrategyType.SINGLE:
            return await OrderService._create_single(user_id, details, db_sess, bus)
        elif details.strategy_type == StrategyType.OCO:
            return await OrderService._create_oco(user_id, details, db_sess, bus)
        elif details.strategy_type == StrategyType.OTO:
            return await OrderService._create_oto(user_id, details, db_sess, bus)
        elif details.strategy_type == StrategyType.OTOCO:
            return await OrderService._create_otoco(user_id, details, db_sess, bus)
        else:
            raise ValueError(f"Unsupported strategy type: {details.strategy_type}")

    @staticmethod
    async def _create_single(
        user_id: uuid.UUID,
        details: SingleOrderCreate,
        db_sess: AsyncSession,
        bus: CommandBus,
    ) -> dict:

        order_id = uuid.uuid4()
        db_order = Orders(
            order_id=order_id,
            user_id=user_id,
            instrument_id=str(details.instrument_id),
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
            instrument_id=details.instrument_id,
            strategy_type=StrategyType.SINGLE,
            **meta.model_dump(),
        )

        await bus.put(command)

        return {"order_id": str(order_id), "status": "accepted"}

    @staticmethod
    async def _create_oco(
        user_id: uuid.UUID,
        details: OCOOrderCreate,
        db_sess: AsyncSession,
        bus: CommandBus,
    ) -> dict:
        group_id = uuid.uuid4()
        legs_meta = []
        response_ids = []

        for leg_details in details.legs:
            leg_id = uuid.uuid4()
            response_ids.append(str(leg_id))

            db_leg = Orders(
                order_id=leg_id,
                user_id=user_id,
                order_group_id=group_id,
                instrument_id=str(details.instrument_id),
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
            instrument_id=details.instrument_id,
            strategy_type=StrategyType.OCO,
            legs=legs_meta,
        )
        await bus.put(command)

        return {"group_id": str(group_id), "order_ids": response_ids}

    @staticmethod
    async def _create_oto(
        user_id: uuid.UUID,
        details: OTOOrderCreate,
        db_sess: AsyncSession,
        bus: CommandBus,
    ) -> dict:
        group_id = uuid.uuid4()

        parent_id = uuid.uuid4()
        db_parent = OrderService._build_db_order(
            user_id, details.instrument_id, details.parent, parent_id
        )
        db_parent.order_group_id = group_id
        db_parent.group_type = StrategyType.OTO
        db_sess.add(db_parent)

        child_id = uuid.uuid4()
        db_child = OrderService._build_db_order(
            user_id, details.instrument_id, details.child, child_id
        )
        db_child.order_group_id = group_id
        db_child.parent_order_id = parent_id
        db_child.group_type = StrategyType.OTO
        db_sess.add(db_child)

        await db_sess.commit()

        command = NewOTOOrderCommand(
            instrument_id=details.instrument_id,
            strategy_type=StrategyType.OTO,
            parent=OrderService._to_meta(parent_id, user_id, details.parent),
            child=OrderService._to_meta(child_id, user_id, details.child),
        )
        await bus.put(command)

        return {
            "group_id": str(group_id),
            "parent_id": str(parent_id),
            "child_id": str(child_id),
        }

    @staticmethod
    async def _create_otoco(
        user_id: uuid.UUID,
        details: OTOCOOrderCreate,
        db_sess: AsyncSession,
        bus: CommandBus,
    ) -> dict:
        group_id = uuid.uuid4()

        parent_id = uuid.uuid4()
        db_parent = OrderService._build_db_order(
            user_id, details.instrument_id, details.parent, parent_id
        )
        db_parent.order_group_id = group_id
        db_parent.group_type = StrategyType.OTOCO
        db_sess.add(db_parent)

        child_ids = []
        legs_meta = []

        for leg_spec in details.oco_legs:
            leg_id = uuid.uuid4()
            child_ids.append(str(leg_id))

            db_leg = OrderService._build_db_order(
                user_id, details.instrument_id, leg_spec, leg_id
            )
            db_leg.order_group_id = group_id
            db_leg.parent_order_id = parent_id
            db_leg.group_type = StrategyType.OTOCO
            db_sess.add(db_leg)

            legs_meta.append(OrderService._to_meta(leg_id, user_id, leg_spec))

        await db_sess.commit()

        command = NewOTOCOOrderCommand(
            instrument_id=details.instrument_id,
            strategy_type=StrategyType.OTOCO,
            parent=OrderService._to_meta(parent_id, user_id, details.parent),
            oco_legs=legs_meta,
        )
        await bus.put(command)

        return {
            "group_id": str(group_id),
            "parent_id": str(parent_id),
            "legs": child_ids,
        }

    @staticmethod
    def _get_instrument_id(symbol: str) -> None: ...

    @staticmethod
    def _build_db_order(
        user_id: uuid.UUID,
        instrument_id: uuid.UUID,
        details: OrderBase,
        order_id: uuid.UUID,
    ) -> Orders:
        """Helper to map API model to DB model."""
        return Orders(
            order_id=order_id,
            user_id=user_id,
            instrument_id=str(instrument_id),
            side=details.side.value,
            order_type=details.order_type.value,
            quantity=details.quantity,
            limit_price=details.limit_price,
            stop_price=details.stop_price,
            status=OrderStatus.PENDING.value,
        )

    @staticmethod
    def _to_meta(
        order_id: uuid.UUID, user_id: uuid.UUID, details: OrderBase
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
