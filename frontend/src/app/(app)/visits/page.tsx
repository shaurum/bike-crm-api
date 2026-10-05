import { CalendarCheck } from "lucide-react";
import { PagePlaceholder } from "@/components/layout/page-placeholder";

export default function VisitsPage() {
  return (
    <PagePlaceholder
      title="Посещения"
      description="Плановые выезды, осмотры байков и задачи по обслуживанию"
      icon={CalendarCheck}
      hint="Скоро здесь будет календарь посещений"
    />
  );
}