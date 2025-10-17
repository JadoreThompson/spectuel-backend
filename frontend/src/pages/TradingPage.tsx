import ActivityLog from "@/components/activity-log";
import OrderForm from "@/components/order-form";
import OrderBook from "@/components/orderbook";
import RecentTrades from "@/components/recent-trades";
import {
  Table,
  TableBody,
  TableCell,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { GripHorizontal, X } from "lucide-react";
import { useState, type FC } from "react";

const OrdersTable: FC = () => {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableCell>Symbol</TableCell>
          <TableCell>Side</TableCell>
          <TableCell>Quantity</TableCell>
          <TableCell>Avg Fill Price</TableCell>
          <TableCell>
            <GripHorizontal />
          </TableCell>
        </TableRow>
      </TableHeader>
      <TableBody>
        <TableRow>
          <TableCell>EURUSD</TableCell>
          <TableCell>Long</TableCell>
          <TableCell>10</TableCell>
          <TableCell>390</TableCell>
          <TableCell>
            <X  color="red" />
          </TableCell>
        </TableRow>
      </TableBody>
    </Table>
  );
};

const TradingPage: FC = () => {
  const [showOrderBook, setShowOrderbook] = useState<boolean>(true);

  return (
    <>
      <header className="z-[2] h-10 w-full fixed top-0 left-0 bg-white">
        Header
      </header>
      <main className="grid grid-cols-10 ro mt-10 pb-5">
        <div className="h-full col-span-8 border-r">
          <div className="h-15 w-full flex bg-green-500 border-t-1">
            
          </div>
          <div className="h-120 w-full flex gap-1 border-y-1">
            <div className="h-full w-3/4 bg-pink-500 border-r"></div>
            <div className="h-full w-1/4 p-1">
              <div className="w-full flex gap-1">
                <span
                  onClick={() => setShowOrderbook(!showOrderBook)}
                  className={`px-2 text-sm font-bold border-b-2 cursor-pointer ${
                    showOrderBook
                      ? "border-b-white"
                      : "border-b-transparent text-muted-foreground"
                  }`}
                >
                  Order book
                </span>
                <span
                  onClick={() => setShowOrderbook(!showOrderBook)}
                  className={`px-2 text-sm font-bold border-b-2 cursor-pointer ${
                    showOrderBook
                      ? "border-b-transparent text-muted-foreground"
                      : "border-b-white"
                  }`}
                >
                  Market trades
                </span>
              </div>
              {showOrderBook ? <OrderBook /> : <RecentTrades />}
            </div>
          </div>
          <div className="h-120 flex-1">
            <OrdersTable />
          </div>
        </div>
        <div className="h-full col-span-2 flex flex-col">
          <div className="h-fit w-full mb-2">
            <OrderForm />
          </div>
          <div className="h-120 w-full border-t pt-2 px-1">
            <span className="text-sm font-semibold">Activity</span>
            <ActivityLog />
          </div>
        </div>
      </main>
    </>
  );
};
export default TradingPage;
