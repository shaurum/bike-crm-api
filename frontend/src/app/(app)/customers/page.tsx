import { Users } from "lucide-react";
import { PagePlaceholder } from "@/components/layout/page-placeholder";

export default function CustomersPage() {
  return (
    <PagePlaceholder
      title="Клиенты"
      description="База клиентов: контакты, документы, история аренды"
      icon={Users}
      hint="Скоро здесь будет реестр клиентов"
    />
  );
}