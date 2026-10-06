import { DocumentsPage } from "@/components/documents/documents-page";

export default function DocumentsRoute() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Документы</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Договоры аренды и подписанные сканы
        </p>
      </div>

      <DocumentsPage />
    </div>
  );
}