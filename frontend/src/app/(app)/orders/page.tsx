import { FunnelBoard } from "@/components/leads/funnel-board";

export default function OrdersPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Заказы</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Воронка продаж: от входящего лида до выдачи байка
        </p>
      </div>

      <FunnelBoard />
    </div>
  );
}