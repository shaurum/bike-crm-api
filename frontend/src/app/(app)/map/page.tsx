import { FleetMap } from "@/components/tracking/fleet-map";

export default function MapPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-xl font-bold tracking-tight">Карта</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Текущее положение всех байков по данным GPS-трекеров
        </p>
      </div>

      <FleetMap />
    </div>
  );
}
