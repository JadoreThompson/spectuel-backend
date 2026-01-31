# Spectuel - High-Performance Trading Engine

Spectuel is an event-driven, distributed trading engine built for high-frequency trading and real-time market data processing. The system is designed with fault tolerance, scalability, and performance as core principles.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Technologies](#technologies)
- [Key Design Decisions](#key-design-decisions)
- [System Components](#system-components)
- [Data Flow](#data-flow)
- [Getting Started](#getting-started)
- [API Documentation](#api-documentation)

## Overview

Spectuel is a complete trading platform that handles:

- Order matching and execution
- Real-time balance management
- Market data distribution
- Event sourcing and replay
- WebSocket streaming for real-time updates

The system is built on an event-driven architecture where all state changes are captured as immutable events, enabling features like:

- Complete audit trails
- System recovery through event replay
- Distributed processing
- Real-time data streaming

## Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Client Layer                             │
│  (Web/Mobile Apps, Trading Terminals, API Consumers)            │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                      FastAPI REST API                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │   Orders     │  │    Users     │  │   Markets    │         │
│  │   Router     │  │   Router     │  │   Router     │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Kafka Message Bus                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │   Commands   │  │    Events    │  │  Instrument  │         │
│  │    Topic     │  │    Topic     │  │    Events    │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
└────────────────────────┬────────────────────────────────────────┘
                         │
         ┌───────────────┼───────────────┐
         ▼               ▼               ▼
┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│   Engine    │  │   Engine    │  │   Engine    │
│  Orchestr.  │  │  Orchestr.  │  │  Orchestr.  │
│  (BTCUSD)   │  │  (ETHUSD)   │  │  (GBPUSD)   │
└──────┬──────┘  └──────┬──────┘  └──────┬──────┘
       │                │                │
       ▼                ▼                ▼
┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│   Matching  │  │   Matching  │  │   Matching  │
│   Engine    │  │   Engine    │  │   Engine    │
└──────┬──────┘  └──────┬──────┘  └──────┬──────┘
       │                │                │
       └────────────────┼────────────────┘
                        ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Event Handlers Layer                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │    Order     │  │   Balance    │  │    Kafka     │         │
│  │   Handler    │  │   Handler    │  │   Fanout     │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Persistence Layer                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │  PostgreSQL  │  │    Redis     │  │  Event Logs  │         │
│  │  (Orders,    │  │  (Balances,  │  │  (Snapshots) │         │
│  │   Users)     │  │   Cache)     │  │              │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
└─────────────────────────────────────────────────────────────────┘
```

### Event Flow Diagram

```
┌──────────┐
│  Client  │
└────┬─────┘
     │ 1. Place Order (REST API)
     ▼
┌────────────────┐
│  Order Router  │
└────┬───────────┘
     │ 2. Publish NewOrderCommand
     ▼
┌─────────────────┐
│  Kafka Commands │
│      Topic      │
└────┬────────────┘
     │ 3. Consume Command
     ▼
┌──────────────────┐
│ Engine Orchestr. │
│  (per symbol)    │
└────┬─────────────┘
     │ 4. Process Command
     ▼
┌──────────────────┐
│ Matching Engine  │
│  (OrderBook)     │
└────┬─────────────┘
     │ 5. Generate Events
     │    - OrderPlacedEvent
     │    - OrderFilledEvent
     │    - BalanceEvents
     ▼
┌──────────────────┐
│  Engine Logger   │
│  (Write-Ahead)   │
└────┬─────────────┘
     │ 6. Log to File
     │ 7. Publish to Kafka
     ▼
┌─────────────────┐
│  Kafka Events   │
│      Topic      │
└────┬────────────┘
     │ 8. Fan out to specific topics
     ▼
┌──────────────────┬──────────────────┐
│  Order Events    │  Balance Events  │
│      Topic       │      Topic       │
└────┬─────────────┴────┬─────────────┘
     │                  │
     │ 9. Consume       │ 9. Consume
     ▼                  ▼
┌──────────────────┐ ┌──────────────────┐
│ Order Handler    │ │ Balance Handler  │
└────┬─────────────┘ └────┬─────────────┘
     │ 10. Update DB     │ 10. Update DB
     ▼                   ▼
┌──────────────────┐ ┌──────────────────┐
│   PostgreSQL     │ │   PostgreSQL     │
│  (Orders table)  │ │ (Balances table) │
└──────────────────┘ └──────────────────┘
     │                   │
     │ 11. Notify via WebSocket
     └───────────┬───────┘
                 ▼
         ┌──────────────┐
         │  WebSocket   │
         │  Connection  │
         │   Manager    │
         └──────┬───────┘
                │ 12. Push to Client
                ▼
         ┌──────────────┐
         │    Client    │
         └──────────────┘
```

## Technologies

### Core Technologies

- **Python 3.11+** - Primary programming language
- **FastAPI** - High-performance async web framework
- **PostgreSQL** - Primary data store for orders, users, and events
- **Redis** - In-memory store for balances, caching, and session management
- **Apache Kafka** - Message broker for event streaming and command distribution
- **SQLAlchemy** - ORM for database interactions
- **Pydantic** - Data validation and serialization
- **WebSockets** - Real-time bidirectional communication

### Supporting Technologies

- **Argon2** - Password hashing
- **PyJWT** - JWT token generation and validation
- **aiokafka** - Async Kafka client
- **asyncpg** - Async PostgreSQL driver
- **Brevo** - Email service integration

## Key Design Decisions

### 1. Event-Driven Architecture

**Decision:** All state changes are represented as immutable events.

**Rationale:**

- Complete audit trail of all system actions
- Enables event replay for system recovery
- Supports distributed processing
- Facilitates debugging and monitoring

**Implementation:**

- Events are logged to disk via `EngineLogger`
- Events are published to Kafka for distribution
- Event handlers update read models (PostgreSQL)

### 2. Strategy Pattern for Order Types

**Decision:** Use the Strategy pattern to handle different order strategy types (Single, OCO, OTO, OTOCO).

**Rationale:**

- Each strategy has unique execution logic
- Enables easy addition of new strategy types
- Separates concerns and improves maintainability
- Reduces conditional complexity in the matching engine

**Implementation:**

```python
# Base strategy interface
class BaseStrategy:
    def execute(self, context: ExecutionContext) -> list[Event]:
        pass

# Concrete strategies
class SingleStrategy(BaseStrategy):
    # Handles simple limit/stop orders

class OCOStrategy(BaseStrategy):
    # One-Cancels-Other: two orders, filling one cancels the other

class OTOStrategy(BaseStrategy):
    # One-Triggers-Other: parent order triggers child order

class OTOCOStrategy(BaseStrategy):
    # Combination of OTO and OCO
```

### 3. Write-Ahead Logging with EngineLogger

**Decision:** Log all events to disk before publishing to Kafka.

**Rationale:**

- Ensures no event loss even if Kafka is unavailable
- Enables system recovery by replaying events from logs
- Provides a source of truth independent of external systems
- Supports snapshotting and state reconstruction

**Implementation:**

- Events are written to timestamped log files
- Log files are rotated periodically
- Shadow engine can replay logs to rebuild state

### 4. Shadow Engine for Snapshotting

**Decision:** Maintain a shadow engine that replays events to create snapshots.

**Rationale:**

- Enables fast engine startup from snapshots
- Reduces replay time for long-running engines
- Provides point-in-time state recovery
- Supports testing and debugging

**How Snapshotting Works:**

1. Shadow engine runs in parallel with main engine
2. Periodically, shadow engine replays all events from logs
3. Once caught up, shadow engine creates a snapshot of current state
4. Snapshot includes: orderbook state, pending orders, balances
5. On restart, engine loads latest snapshot and replays events since snapshot
6. This dramatically reduces startup time

### 5. LUA Scripts for Balance Management

**Decision:** Use Redis LUA scripts for balance operations in `BalanceManager`.

**Rationale:**

- **Atomicity:** LUA scripts execute atomically in Redis
- **Idempotency:** Can safely retry operations without double-counting
- **Synchronization:** Prevents race conditions in concurrent balance updates
- **Performance:** Reduces network round-trips

**Implementation:**

```python
# Example LUA script for balance increase
INCREASE_BALANCE_SCRIPT = """
local key = KEYS[1]
local amount = tonumber(ARGV[1])
local command_id = ARGV[2]

-- Check if command already processed
if redis.call('HEXISTS', key .. ':processed', command_id) == 1 then
    return 0  -- Already processed, idempotent
end

-- Increase balance
redis.call('INCRBYFLOAT', key, amount)

-- Mark command as processed
redis.call('HSET', key .. ':processed', command_id, '1')

return 1
```

### 6. Heartbeat System for Engine Health

**Decision:** Implement a heartbeat server to monitor engine health.

**Rationale:**

- Detects crashed or unresponsive engines
- Enables automatic failover
- Provides visibility into system health
- Supports graceful shutdown

**How It Works:**

1. Each engine orchestrator registers with heartbeat server on startup
2. Engines send periodic heartbeat messages (every 2-3 seconds)
3. Heartbeat server tracks last heartbeat time for each engine
4. If no heartbeat received within timeout (5 seconds), engine marked as dead
5. Dead engines trigger alerts and can be automatically restarted
6. Instrument status updated in database (ALIVE/DEAD)

### 7. Distributed Architecture

**Decision:** Each trading instrument (symbol) has its own engine orchestrator.

**Rationale:**

- **Scalability:** Engines can run on different machines
- **Isolation:** Failure in one engine doesn't affect others
- **Performance:** Parallel processing of different symbols
- **Resource Management:** Can allocate resources per symbol based on volume

**Implementation:**

- Command: `engine run BTCUSD` starts engine for BTCUSD
- Each engine:
  - Consumes commands for its symbol from Kafka
  - Maintains its own orderbook
  - Generates events for its symbol
  - Logs events independently

## System Components

### 1. Engine Orchestrator

The engine orchestrator is the core component that coordinates order processing for a specific trading instrument.

**Responsibilities:**

- Consume commands from Kafka
- Validate commands
- Delegate to matching engine
- Generate events
- Log events via EngineLogger
- Publish events to Kafka
- Send heartbeats

**Startup Process (`engine run`):**

1. Load configuration and connect to services (Kafka, Redis, PostgreSQL)
2. If snapshots exists:
   - Load snapshots into memory
   - Replay events since snapshots timestamp
3. If no snapshots:
   - Replay all events from logs
4. Register with heartbeat server
5. Start consuming commands from Kafka
6. Begin processing orders

### 2. Matching Engine

The matching engine implements the core order matching logic.

**Features:**

- Price-time priority matching
- Support for limit and stop orders
- Partial fills
- Order modification and cancellation
- Balance validation before execution

**Order Book Structure:**

```
Bids (Buy Orders)          Asks (Sell Orders)
Price    Quantity          Price    Quantity
43270.0  1.5              43270.5  1.2
43269.5  2.3              43271.0  3.1
43269.0  0.8              43271.5  0.5
```

### 3. Balance Manager

Manages user balances using Redis for high performance.

**Features:**

- Atomic balance operations via LUA scripts
- Idempotent command processing
- Escrow management for pending orders
- Cash and asset balance tracking

**Balance Types:**

- **Cash Balance:** Available cash for trading
- **Cash Escrow:** Cash locked in pending orders
- **Asset Balance:** Available assets (e.g., BTC, ETH)
- **Asset Escrow:** Assets locked in pending orders

### 4. Event Handlers

Event handlers consume events from Kafka and update read models.

**Order Event Handler:**

- Updates order status in PostgreSQL
- Tracks order execution history
- Maintains order audit trail

**Balance Event Handler:**

- Updates asset balances in PostgreSQL
- Tracks balance changes
- Maintains balance audit trail

**Kafka Fanout:**

- Consumes from main events topic
- Routes events to specific topics (orders, balances, instruments)
- Updates price cache in Redis

### 5. WebSocket Managers

Provide real-time data streaming to clients.

**Orders WebSocket:**

- Authenticated connections
- Subscribe to order and balance events
- Real-time order updates
- Real-time balance updates

**Markets WebSocket:**

- Public connections (no auth required)
- Subscribe to market data (trades, bars, orderbook)
- Real-time price updates
- OHLC bar updates

## Data Flow

### Order Placement Flow

1. **Client** sends POST request to `/orders/` with order details
2. **Order Router** validates request and creates `NewOrderCommand`
3. **Order Router** publishes command to Kafka `commands` topic
4. **Engine Orchestrator** consumes command for the symbol
5. **Engine Orchestrator** validates command (balance check, etc.)
6. **Matching Engine** attempts to match order against orderbook
7. **Matching Engine** generates events:
   - `OrderPlacedEvent` (always)
   - `OrderFilledEvent` or `OrderPartiallyFilledEvent` (if matched)
   - `BalanceEvents` (cash/asset escrow changes)
   - `TradeEvent` (if matched)
8. **Engine Logger** writes events to log file (write-ahead)
9. **Engine Orchestrator** publishes events to Kafka `engine_events` topic
10. **Kafka Fanout** routes events to specific topics
11. **Event Handlers** consume events and update PostgreSQL
12. **WebSocket Manager** pushes events to subscribed clients
13. **Client** receives real-time updates

### Balance Update Flow

1. **Matching Engine** generates balance event (e.g., `CashEscrowIncreased`)
2. **Event** logged and published to Kafka
3. **Balance Event Handler** consumes event
4. **Balance Event Handler** updates `AssetBalances` table in PostgreSQL
5. **Balance Manager** (in engine) updates Redis using LUA script
6. **WebSocket** pushes balance update to user's connection

### Market Data Flow

1. **Matching Engine** generates `TradeEvent` when orders match
2. **Event** published to Kafka `instrument_events` topic
3. **OHLC Builder** consumes trade events
4. **OHLC Builder** aggregates trades into OHLC bars (1m, 5m, 15m, 1h, 4h, 1d)
5. **OHLC Builder** stores bars in PostgreSQL
6. **OHLC Builder** publishes `BarUpdateEvent` to Kafka
7. **Markets WebSocket** pushes bar updates to subscribed clients
8. **Orderbook Publisher** periodically snapshots orderbook
9. **Orderbook Publisher** publishes `OrderbookSnapshotEvent`
10. **Markets WebSocket** pushes orderbook updates to subscribed clients

## Getting Started

### Prerequisites

- Python 3.11+
- PostgreSQL 14+
- Redis 7+
- Apache Kafka 3.0+

### Installation

1. Clone the repository:

```bash
git clone https://github.com/yourusername/spectuel-backend.git
cd spectuel-backend
```

2. Create virtual environment:

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Set up environment variables:

```bash
cp .env.example .env
# Edit .env with your configuration
```

3. Initialize database:

```bash
# Run migrations
uv run alembic upgrade head
```

6. Start services:

```bash
# Terminal 1
uv run src/main.py http run

# Terminal 2
uv run src/main.py heartbeat run

# Terminal 3
uv run src/main.py engine run
```

### Running Tests

```bash
uv run pytest -s -x
```

## API Documentation

### REST API

- **Orders:** `/orders/` - Create, modify, cancel orders
- **Users:** `/user/` - User profile, balances, events
- **Markets:** `/markets/` - Market data, OHLC bars, symbols
- **Auth:** `/auth/` - Authentication, registration

### WebSocket APIs

- **Orders WebSocket:** `ws://localhost:8000/ws/orders/`
  - Real-time order and balance updates
  - Requires authentication
  - See [docs/orders-websocket.md](docs/orders-websocket.md)

- **Markets WebSocket:** `ws://localhost:8000/ws/markets`
  - Real-time market data (trades, bars, orderbook)
  - No authentication required
  - See [docs/markets-websocket.md](docs/markets-websocket.md)

## Project Structure

```
spectuel-backend/
├── src/
│   ├── api/                    # FastAPI application
│   │   ├── routers/           # API route handlers
│   │   │   ├── auth/          # Authentication endpoints
│   │   │   ├── orders/        # Order management endpoints
│   │   │   ├── users/         # User endpoints
│   │   │   └── markets/       # Market data endpoints
│   │   ├── ws/                # WebSocket handlers
│   │   └── app.py             # FastAPI app initialization
│   ├── engine/                # Trading engine core
│   │   ├── matching_engines/  # Order matching logic
│   │   ├── orders/            # Order models
│   │   ├── strategies/        # Order strategy implementations
│   │   ├── services/          # Engine services
│   │   │   ├── balance_manager.py
│   │   │   └── order_book_publisher.py
│   │   ├── engine_orchestrator/ # Engine coordination
│   │   ├── restoration/       # Snapshot and replay logic
│   │   ├── events/            # Event definitions
│   │   ├── commands.py        # Command definitions
│   │   └── loggers/           # EngineLogger implementation
│   ├── services/              # Application services
│   │   ├── event_handlers/    # Event consumers
│   │   ├── email/             # Email service
│   │   ├── jwt/               # JWT service
│   │   └── ohlc_builder/      # OHLC aggregation
│   ├── infra/                 # Infrastructure
│   │   ├── db/                # Database utilities
│   │   ├── kafka/             # Kafka clients
│   │   └── redis/             # Redis clients
│   ├── runners/               # Service runners
│   ├── cli/                   # CLI commands
│   ├── db_models.py           # SQLAlchemy models
│   ├── enums.py               # Shared enumerations
│   └── config.py              # Configuration
├── tests/                     # Test suite
├── docs/                      # Documentation
├── alembic/                   # Database migrations
├── .env.example               # Environment template
└── README.md                  # This file
```

## Support

For questions or issues, please open an issue on GitHub or contact jadorethomspon6@gmail.com.
