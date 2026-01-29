# Orders WebSocket API Documentation

## Overview

The Orders WebSocket API provides real-time streaming of order and balance events for authenticated users. Clients can subscribe to specific event types to receive updates about their orders and account balances.

**Endpoint:** `ws://your-domain/ws/orders/`

## Authentication

### Step 1: Get WebSocket Token

Before connecting to the WebSocket, you must obtain a temporary authentication token from the REST API.

**Endpoint:** `GET /auth/ws-token`

**Headers:**

- `Cookie: jwt=<your-jwt-token>` (or Authorization header with JWT)

**Example:**

```bash
curl -X GET "http://localhost:8000/auth/ws-token" \
  -H "Cookie: jwt=your-jwt-token"
```

**Response:**

```json
{
  "token": "A1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6"
}
```

**Important:**

- Token expires in **10 seconds** after generation
- Token is single-use only (deleted after first use)
- Generate a new token for each WebSocket connection

### Step 2: Connect and Authenticate

Connect to the WebSocket and send the authentication token within 10 seconds.

**Authentication Message:**

```json
{
  "token": "A1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6"
}
```

**Example:**

```javascript
// Step 1: Get token from REST API
const tokenResponse = await fetch("http://localhost:8000/auth/ws-token", {
  credentials: "include", // Include cookies
});
const { token } = await tokenResponse.json();

// Step 2: Connect to WebSocket
const ws = new WebSocket("ws://localhost:8000/ws/orders/");

ws.onopen = () => {
  // Send authentication token immediately
  ws.send(JSON.stringify({ token }));
};
```

**Authentication Errors:**

If authentication fails, the connection will be closed with an error:

```json
{
  "type": "error",
  "message": "Invalid or expired token"
}
```

**Common Authentication Errors:**

- `"Token is required"` - No token provided
- `"Invalid or expired token"` - Token not found in Redis or expired
- `"Authentication timeout"` - Token not sent within 10 seconds
- `"Already authenticated"` - Attempting to authenticate again

## Subscription Management

After authentication, you can subscribe to order and balance events.

### Subscribe Request

Add event types to your subscription list. Subscriptions are **additive** - new subscriptions are added to existing ones.

**Request Format:**

```json
{
  "type": "subscribe",
  "order_events": ["placed", "filled", "partially_filled"],
  "balance_events": ["cash_balance_increased", "asset_balance_increased"]
}
```

**Fields:**

- `type` (string, required): Must be `"subscribe"`
- `order_events` (array of strings, optional): Order event types to subscribe to
- `balance_events` (array of strings, optional): Balance event types to subscribe to

**Available Order Event Types:**

- `"placed"` - Order successfully placed
- `"partially_filled"` - Order partially executed
- `"filled"` - Order fully executed
- `"modified"` - Order price/quantity modified
- `"modify_rejected"` - Order modification rejected
- `"order_cancelled"` - Order cancelled

**Available Balance Event Types:**

- `"cash_balance_increased"` - Cash balance increased
- `"cash_balance_decreased"` - Cash balance decreased
- `"cash_escrow_increased"` - Cash moved to escrow
- `"cash_escrow_decreased"` - Cash released from escrow
- `"asset_balance_increased"` - Asset quantity increased
- `"asset_balance_decreased"` - Asset quantity decreased
- `"asset_escrow_increased"` - Asset moved to escrow
- `"asset_escrow_decreased"` - Asset released from escrow
- `"asset_balance_snapshot"` - Asset balance snapshot
- `"ask_settled"` - Ask order settled
- `"bid_settled"` - Bid order settled

**Response:**

```json
{
  "type": "ack",
  "request_type": "subscribe",
  "subscriptions": {
    "order_events": ["placed", "filled", "partially_filled"],
    "balance_events": ["cash_balance_increased", "asset_balance_increased"]
  }
}
```

### Unsubscribe Request

Remove specific event types from your subscription list.

**Request Format:**

```json
{
  "type": "unsubscribe",
  "order_events": ["placed"],
  "balance_events": ["cash_balance_increased"]
}
```

**Response:**

```json
{
  "type": "ack",
  "request_type": "unsubscribe",
  "subscriptions": {
    "order_events": ["filled", "partially_filled"],
    "balance_events": ["asset_balance_increased"]
  }
}
```

## Event Types

### Order Events

Order events are sent when your orders change state.

**Order Placed Event:**

```json
{
  "type": "placed",
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "version": 1,
  "order_id": "123e4567-e89b-12d3-a456-426614174000",
  "command_id": "789e0123-e45b-67c8-d901-234567890abc",
  "symbol": "BTCUSD",
  "executed_quantity": 0.0,
  "quantity": 1.5,
  "price": 43250.5,
  "side": "buy",
  "timestamp": 1706745612
}
```

**Order Filled Event:**

```json
{
  "type": "filled",
  "id": "550e8400-e29b-41d4-a716-446655440001",
  "version": 1,
  "order_id": "123e4567-e89b-12d3-a456-426614174000",
  "command_id": "789e0123-e45b-67c8-d901-234567890abc",
  "symbol": "BTCUSD",
  "executed_quantity": 1.5,
  "quantity": 1.5,
  "price": 43250.5,
  "timestamp": 1706745620
}
```

**Order Partially Filled Event:**

```json
{
  "type": "partially_filled",
  "id": "550e8400-e29b-41d4-a716-446655440002",
  "version": 1,
  "order_id": "123e4567-e89b-12d3-a456-426614174000",
  "command_id": "789e0123-e45b-67c8-d901-234567890abc",
  "symbol": "BTCUSD",
  "executed_quantity": 0.8,
  "quantity": 1.5,
  "price": 43250.5,
  "timestamp": 1706745618
}
```

**Order Modified Event:**

```json
{
  "type": "modified",
  "id": "550e8400-e29b-41d4-a716-446655440003",
  "version": 1,
  "order_id": "123e4567-e89b-12d3-a456-426614174000",
  "command_id": "789e0123-e45b-67c8-d901-234567890abc",
  "limit_price": 43300.0,
  "stop_price": null,
  "timestamp": 1706745625
}
```

**Order Cancelled Event:**

```json
{
  "type": "order_cancelled",
  "id": "550e8400-e29b-41d4-a716-446655440004",
  "version": 1,
  "order_id": "123e4567-e89b-12d3-a456-426614174000",
  "command_id": "789e0123-e45b-67c8-d901-234567890abc",
  "symbol": "BTCUSD",
  "timestamp": 1706745630
}
```

### Balance Events

Balance events are sent when your account balances change.

**Cash Balance Increased Event:**

```json
{
  "type": "cash_balance_increased",
  "id": "660e9500-f30c-52e5-b827-557766551111",
  "version": 1,
  "user_id": "user-uuid-here",
  "command_id": "890e1234-f56c-78d9-e012-345678901def",
  "amount": 10000.0,
  "symbol": null,
  "timestamp": 1706745600
}
```

**Asset Balance Increased Event:**

```json
{
  "type": "asset_balance_increased",
  "id": "770ea611-g41d-63f6-c938-668877662222",
  "version": 1,
  "user_id": "user-uuid-here",
  "command_id": "901e2345-g67d-89ea-f123-456789012ghi",
  "symbol": "BTCUSD",
  "amount": 1.5,
  "timestamp": 1706745620
}
```

**Bid Settled Event:**

```json
{
  "type": "bid_settled",
  "id": "880eb722-h52e-74g7-d049-779988773333",
  "version": 1,
  "user_id": "user-uuid-here",
  "command_id": "012e3456-h78e-90fb-g234-567890123hij",
  "symbol": "BTCUSD",
  "cash_escrow_decreased": {
    "amount": 64875.75
  },
  "asset_balance_increased": {
    "amount": 1.5
  },
  "timestamp": 1706745625
}
```

## Error Handling

### Error Response

```json
{
  "type": "error",
  "message": "Invalid JSON format"
}
```

**Common Errors:**

- `"Invalid JSON format"` - Malformed JSON in request
- `"Token is required"` - Authentication token missing
- `"Invalid or expired token"` - Token validation failed
- `"Authentication timeout"` - Token not sent within 10 seconds
- `"Already authenticated"` - Attempting to re-authenticate
- `"Connection for user 'xxx' not found"` - User not connected (internal error)

### Connection Management

**Automatic Disconnection:**

The server will disconnect clients that:

- Fail to authenticate within 10 seconds
- Send messages that timeout (5-second send timeout)
- Experience network errors
- Have their connection replaced by a new connection (only one connection per user)

**Reconnection:**

If disconnected, you must:

1. Get a new WebSocket token from `/auth/ws-token`
2. Establish a new WebSocket connection
3. Authenticate with the new token
4. Re-subscribe to desired events

## Complete Example

```javascript
class OrdersWebSocket {
  constructor(apiUrl) {
    this.apiUrl = apiUrl;
    this.ws = null;
    this.subscriptions = {
      order_events: [],
      balance_events: [],
    };
  }

  async connect() {
    // Step 1: Get WebSocket token
    const response = await fetch(`${this.apiUrl}/auth/ws-token`, {
      credentials: "include",
    });

    if (!response.ok) {
      throw new Error("Failed to get WebSocket token");
    }

    const { token } = await response.json();

    // Step 2: Connect to WebSocket
    this.ws = new WebSocket(`${this.apiUrl.replace("http", "ws")}/ws/orders/`);

    this.ws.onopen = () => {
      console.log("WebSocket connected");

      // Step 3: Authenticate
      this.ws.send(JSON.stringify({ token }));
    };

    this.ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      this.handleMessage(data);
    };

    this.ws.onerror = (error) => {
      console.error("WebSocket error:", error);
    };

    this.ws.onclose = (event) => {
      console.log("WebSocket closed:", event.code, event.reason);
      // Implement reconnection logic here
    };
  }

  handleMessage(data) {
    switch (data.type) {
      case "ack":
        console.log("Subscription acknowledged:", data.subscriptions);
        this.subscriptions = data.subscriptions;
        break;

      case "error":
        console.error("Error:", data.message);
        break;

      // Order events
      case "placed":
        console.log("Order placed:", data);
        break;

      case "filled":
        console.log("Order filled:", data);
        break;

      case "partially_filled":
        console.log("Order partially filled:", data);
        break;

      case "order_cancelled":
        console.log("Order cancelled:", data);
        break;

      // Balance events
      case "cash_balance_increased":
        console.log("Cash balance increased:", data.amount);
        break;

      case "asset_balance_increased":
        console.log(`Asset balance increased: ${data.amount} ${data.symbol}`);
        break;

      case "bid_settled":
      case "ask_settled":
        console.log("Order settled:", data);
        break;

      default:
        console.log("Unknown event type:", data.type);
    }
  }

  subscribe(orderEvents = [], balanceEvents = []) {
    const message = {
      type: "subscribe",
      order_events: orderEvents,
      balance_events: balanceEvents,
    };
    this.ws.send(JSON.stringify(message));
  }

  unsubscribe(orderEvents = [], balanceEvents = []) {
    const message = {
      type: "unsubscribe",
      order_events: orderEvents,
      balance_events: balanceEvents,
    };
    this.ws.send(JSON.stringify(message));
  }

  disconnect() {
    if (this.ws) {
      this.ws.close();
    }
  }
}

// Usage
const ordersWs = new OrdersWebSocket("http://localhost:8000");

await ordersWs.connect();

// Subscribe to order events
ordersWs.subscribe(
  ["placed", "filled", "partially_filled", "order_cancelled"],
  [
    "cash_balance_increased",
    "asset_balance_increased",
    "bid_settled",
    "ask_settled",
  ],
);

// Later, unsubscribe from some events
ordersWs.unsubscribe(["placed"], []);
```

## Best Practices

1. **Token Management**
   - Request token immediately before connecting
   - Don't reuse tokens (they're single-use)
   - Handle token expiration (10 seconds)

2. **Subscription Management**
   - Subscribe only to events you need
   - Use additive subscriptions to build up your event list
   - Unsubscribe from events you no longer need

3. **Connection Management**
   - Implement automatic reconnection with exponential backoff
   - Store subscription state to resubscribe after reconnection
   - Handle only one connection per user (new connections replace old ones)

4. **Error Handling**
   - Always parse JSON with try-catch
   - Handle all event types to avoid missing data
   - Log unknown event types for debugging

5. **Performance**
   - Process events asynchronously
   - Avoid blocking the message handler
   - Consider batching UI updates

## Security

- **Authentication Required:** All connections must authenticate with a valid JWT-derived token
- **User Isolation:** Users only receive events for their own orders and balances
- **Token Security:** Tokens expire in 10 seconds and are single-use
- **Connection Limit:** One WebSocket connection per user (new connections replace old)

## Rate Limits

- No explicit rate limits on subscriptions
- 5-second send timeout for slow consumers
- 10-second authentication timeout
- Server may disconnect unresponsive clients

## Related Endpoints

### REST API - Get User Events

**Endpoint:** `GET /user/events`

Retrieve historical order and balance events.

**Query Parameters:**

- `type` (required): "order" or "balance"
- `symbol` (optional): Filter by symbol
- `skip` (optional): Pagination offset (default: 0)
- `limit` (optional): Results per page (default: 100, max: 100)

**Example:**

```bash
curl "http://localhost:8000/user/events?type=order&symbol=BTCUSD&limit=50" \
  -H "Cookie: jwt=your-jwt-token"
```

### REST API - Get Asset Balances

**Endpoint:** `GET /user/asset-balances`

Retrieve current asset balances.

**Query Parameters:**

- `symbols` (optional): Comma-separated list of symbols to filter

**Example:**

```bash
curl "http://localhost:8000/user/asset-balances?symbols=BTCUSD,ETHUSD" \
  -H "Cookie: jwt=your-jwt-token"
```
