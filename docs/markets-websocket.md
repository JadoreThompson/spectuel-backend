# Markets WebSocket API Documentation

## Overview

The Markets WebSocket API provides real-time market data streaming for trading instruments. Clients can subscribe to multiple data types including OHLC bars, trades, and orderbook snapshots.

**Endpoint:** `ws://your-domain/ws/markets`

## Connection

### Establishing Connection

Connect to the WebSocket endpoint without authentication:

```javascript
const ws = new WebSocket("ws://localhost:8000/ws/markets");

ws.onopen = () => {
  console.log("Connected to markets WebSocket");
};
```

## Subscription Management

### Subscribe Request

Send a subscription request to start receiving market data. Each new subscription request **replaces** all previous subscriptions for that connection.

**Request Format:**

```json
{
  "type": "subscribe",
  "orderbooks": ["BTCUSD", "ETHUSD"],
  "trades": ["BTCUSD", "ETHUSD"],
  "bars": [
    {
      "symbol": "BTCUSD",
      "timeframes": ["1m", "5m", "1h"]
    },
    {
      "symbol": "ETHUSD",
      "timeframes": ["1m", "1h"]
    }
  ]
}
```

**Fields:**

- `type` (string, required): Must be `"subscribe"`
- `orderbooks` (array of strings, optional): List of symbols to receive orderbook snapshots
- `trades` (array of strings, optional): List of symbols to receive trade events
- `bars` (array of objects, optional): List of bar subscriptions with symbol and timeframes

**Available Timeframes:**

- `"1m"` - 1 minute
- `"5m"` - 5 minutes
- `"15m"` - 15 minutes
- `"1h"` - 1 hour
- `"4h"` - 4 hours
- `"1d"` - 1 day

**Response:**

```json
{
  "type": "ack",
  "request_type": "subscribe",
  "subscriptions": {
    "orderbooks": ["BTCUSD", "ETHUSD"],
    "trades": ["BTCUSD", "ETHUSD"],
    "bars": [
      {
        "symbol": "BTCUSD",
        "timeframes": ["1m", "5m", "1h"]
      },
      {
        "symbol": "ETHUSD",
        "timeframes": ["1m", "1h"]
      }
    ]
  }
}
```

### Updating Subscriptions

To change subscriptions, send a new subscribe request. The new request will completely replace the previous subscriptions.

```javascript
// Initial subscription
ws.send(
  JSON.stringify({
    type: "subscribe",
    trades: ["BTCUSD"],
  }),
);

// Update subscription (replaces previous)
ws.send(
  JSON.stringify({
    type: "subscribe",
    trades: ["ETHUSD", "AAPL"],
  }),
);
// Now only receiving trades for ETHUSD and AAPL
```

## Event Types

### 1. Bar Update Event

Sent when an OHLC bar is updated or completed.

```json
{
  "type": "bar_update",
  "symbol": "BTCUSD",
  "timeframe": "1m",
  "timestamp": 1706745600,
  "open": 43250.5,
  "high": 43280.0,
  "low": 43240.0,
  "close": 43270.25
}
```

**Fields:**

- `type`: Always `"bar_update"`
- `symbol`: Trading symbol
- `timeframe`: Bar timeframe (e.g., "1m", "5m", "1h")
- `timestamp`: Unix timestamp of bar start time
- `open`: Opening price
- `high`: Highest price
- `low`: Lowest price
- `close`: Current/closing price

### 2. Trade Event

Sent when a new trade occurs.

```json
{
  "type": "new_trade",
  "symbol": "BTCUSD",
  "price": 43270.25,
  "quantity": 0.5,
  "timestamp": 1706745612.345,
  "side": "buy"
}
```

**Fields:**

- `type`: Always `"new_trade"`
- `symbol`: Trading symbol
- `price`: Trade execution price
- `quantity`: Trade quantity
- `timestamp`: Unix timestamp with milliseconds
- `side`: Trade side ("buy" or "sell")

### 3. Orderbook Snapshot Event

Sent periodically with the current orderbook state.

```json
{
  "type": "orderbook_snapshot",
  "symbol": "BTCUSD",
  "bids": [
    [43270.0, 1.5],
    [43269.5, 2.3],
    [43269.0, 0.8]
  ],
  "asks": [
    [43270.5, 1.2],
    [43271.0, 3.1],
    [43271.5, 0.5]
  ]
}
```

**Fields:**

- `type`: Always `"orderbook_snapshot"`
- `symbol`: Trading symbol
- `bids`: Array of [price, quantity] pairs, sorted by price descending
- `asks`: Array of [price, quantity] pairs, sorted by price ascending

## Error Handling

### Error Response

```json
{
  "type": "error",
  "message": "Invalid JSON"
}
```

**Common Errors:**

- `"Invalid JSON"` - Malformed JSON in request
- `"Unknown request type"` - Invalid request type
- `"Invalid timeframe: xyz"` - Unsupported timeframe value

### Connection Errors

The server will automatically disconnect clients that:

- Fail to send messages within 5 seconds (timeout)
- Experience network errors
- Send malformed requests repeatedly

## Complete Example

```javascript
const ws = new WebSocket("ws://localhost:8000/ws/markets");

ws.onopen = () => {
  console.log("Connected");

  // Subscribe to multiple data types
  ws.send(
    JSON.stringify({
      type: "subscribe",
      orderbooks: ["BTCUSD"],
      trades: ["BTCUSD", "ETHUSD"],
      bars: [
        {
          symbol: "BTCUSD",
          timeframes: ["1m", "5m", "1h"],
        },
      ],
    }),
  );
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);

  switch (data.type) {
    case "bar_update":
      console.log(`Bar update for ${data.symbol} ${data.timeframe}:`, {
        open: data.open,
        high: data.high,
        low: data.low,
        close: data.close,
        timestamp: new Date(data.timestamp * 1000),
      });
      break;

    case "new_trade":
      console.log(`Trade on ${data.symbol}:`, {
        price: data.price,
        quantity: data.quantity,
        side: data.side,
        timestamp: new Date(data.timestamp * 1000),
      });
      break;

    case "orderbook_snapshot":
      console.log(`Orderbook for ${data.symbol}:`, {
        bestBid: data.bids[0],
        bestAsk: data.asks[0],
      });
      break;

    case "error":
      console.error("Error:", data.message);
      break;
  }
};

ws.onerror = (error) => {
  console.error("WebSocket error:", error);
};

ws.onclose = () => {
  console.log("Disconnected");
};
```

## Best Practices

1. **Subscription Management**
   - Only subscribe to symbols and timeframes you need
   - Update subscriptions by sending a new complete subscribe request
   - Unsubscribe from all by sending an empty subscribe request

2. **Message Handling**
   - Always parse JSON with try-catch
   - Handle all event types to avoid missing data
   - Log unknown event types for debugging

3. **Connection Management**
   - Implement reconnection logic with exponential backoff
   - Store subscription state to resubscribe after reconnection
   - Handle connection timeouts gracefully

4. **Performance**
   - Avoid subscribing to too many symbols simultaneously
   - Use appropriate timeframes (higher timeframes = fewer updates)
   - Process messages asynchronously to avoid blocking

## Rate Limits

- No authentication required
- No explicit rate limits on subscriptions
- Server may disconnect slow consumers (5-second send timeout)
- Maximum 500 bars per REST API request

## Related Endpoints

### REST API - Get Historical Bars

**Endpoint:** `GET /markets/{symbol}/bars`

Retrieve historical OHLC data with pagination.

**Query Parameters:**

- `timeframe` (required): Timeframe (1m, 5m, 15m, 1h, 4h, 1d)
- `start_date` (optional): Unix timestamp start
- `end_date` (optional): Unix timestamp end
- `next_page_token` (optional): Pagination token

**Example:**

```bash
curl "http://localhost:8000/markets/BTCUSD/bars?timeframe=1h&start_date=1706745600"
```

**Response:**

```json
{
  "bars": [
    {
      "symbol": "BTCUSD",
      "timeframe": "1h",
      "timestamp": 1706745600,
      "open": 43250.5,
      "high": 43280.0,
      "low": 43240.0,
      "close": 43270.25
    }
  ],
  "next_page_token": "eyJzdGFydF9kYXRlIjogMTcwNjc0OTIwMX0="
}
```

**Lookback Limits:**

- 1m: 7 days
- 5m: 14 days
- 15m: 30 days
- 1h: 90 days
- 4h: 180 days
- 1d: 365 days
