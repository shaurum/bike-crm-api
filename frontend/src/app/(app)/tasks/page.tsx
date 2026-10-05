import { ListChecks } from "lucide-react";
import { PagePlaceholder } from "@/components/layout/page-placeholder";

export default function TasksPage() {
  return (
    <PagePlaceholder
      title="Задачи"
      description="Задачи по лидам, броням и обслуживанию байков"
      icon={ListChecks}
      hint="Скоро здесь будет список задач"
    />
  );
}