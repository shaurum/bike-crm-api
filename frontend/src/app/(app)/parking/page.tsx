import { ParkingGarage } from "@/components/bikes/parking-garage";

export default function ParkingPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Парковка</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Гараж устройств: характеристики, прайс и статус аренды
        </p>
      </div>

      <ParkingGarage />
    </div>
  );
}