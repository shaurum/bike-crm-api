import { CustomersList } from "@/components/customers/customers-list";

export default function CustomersPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Клиенты</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Паспортные данные и сканы документов для договоров аренды
        </p>
      </div>

      <CustomersList />
    </div>
  );
}