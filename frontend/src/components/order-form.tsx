import { useState } from "react";
import { Button } from "./ui/button";
import { Input } from "./ui/input";

const OrderForm = () => {
  const [side, setSide] = useState("bid");
  const [orderType, setOrderType] = useState("market");

  // --- ADDED: form state + handler (no existing lines changed) ---
  const [formData, setFormData] = useState({
    amount: "",
    price: "",
    stopPrice: "",
  });

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
  };
  // --- end added ---

  return (
    <div className="h-auto w-full p-1 bg-background">
      <div className="h-10 w-full flex gap-1 p-1 bg-secondary rounded-sm">
        <div className="h-full w-1/2 flex items-center">
          <Button
            variant="ghost"
            onClick={() => setSide("bid")}
            className={`h-full w-full focus:!outline-none ${
              side === "bid"
                ? "!bg-green-400 hover:!bg-green-500"
                : "!bg-transparent text-muted-foreground"
            }`}
          >
            Buy
          </Button>
        </div>
        <div className="h-full w-1/2 flex items-center">
          <Button
            variant="ghost"
            onClick={() => setSide("ask")}
            className={`h-full w-full focus:!outline-none ${
              side === "ask"
                ? "!bg-red-400 hover:!bg-red-500"
                : "!bg-transparent text-muted-foreground"
            }`}
          >
            Sell
          </Button>
        </div>
      </div>
      <div className="h-10 w-full">
        {["market", "limit", "stop"].map((val) => (
          <Button
            variant="ghost"
            onClick={() => setOrderType(val)}
            className={`!bg-transparent !border-b-2 !rounded-none focus:!outline-none ${
              orderType === val
                ? "!border-b-white text-primary"
                : "!border-b-transparent text-muted-foreground"
            }`}
          >
            {val.charAt(0).toUpperCase() + val.slice(1)}
          </Button>
        ))}
      </div>

      {/* --- ADDED: Form content for each order type (keeps existing layout intact) --- */}
      <div className="mt-2">
        {/* Amount is common */}
        <Input
          name="amount"
          type="number"
          placeholder="Amount"
          value={formData.amount}
          onChange={handleChange}
          className="w-full p-1 rounded-sm mb-2 bg-white/5 border border-border text-sm"
        />

        {/* Limit order: show Price */}
        {orderType === "limit" && (
          <Input
            name="price"
            type="number"
            placeholder="Limit Price"
            value={formData.price}
            onChange={handleChange}
            className="w-full p-1 rounded-sm mb-2 bg-white/5 border border-border text-sm"
          />
        )}

        {/* Stop order: show Stop Price and optional Limit Price */}
        {orderType === "stop" && (
          <>
            <Input
              name="stopPrice"
              type="number"
              placeholder="Stop Price"
              value={formData.stopPrice}
              onChange={handleChange}
              className="w-full p-1 rounded-sm mb-2 bg-white/5 border border-border text-sm"
            />
          </>
        )}

        <Button
          className={`w-full text-white ${
            side === "bid"
              ? "!bg-green-500 hover:!bg-green-600"
              : "!bg-red-500 hover:!bg-red-600"
          }`}
        >
          {side === "bid" ? "Place" : "Place"}
        </Button>
      </div>
    </div>
  );
};

export default OrderForm;
