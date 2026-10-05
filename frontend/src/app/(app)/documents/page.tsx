import { FileText } from "lucide-react";
import { PagePlaceholder } from "@/components/layout/page-placeholder";

export default function DocumentsPage() {
  return (
    <PagePlaceholder
      title="Документы"
      description="Договоры аренды, шаблоны и сгенерированные PDF"
      icon={FileText}
      hint="Скоро здесь будут договоры и шаблоны"
    />
  );
}