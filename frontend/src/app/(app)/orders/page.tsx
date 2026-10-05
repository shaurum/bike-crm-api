import { ClipboardList } from "lucide-react";
import { PagePlaceholder } from "@/components/layout/page-placeholder";

export default function OrdersPage() {
  return (
    <PagePlaceholder
      title="Заказы"
      description="Брони проката: статус, оплата, выдача и возврат байков"
      icon={ClipboardList}
      hint="Скоро здесь будет список заказов с фильтрами"
    />
  );
}