"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";

import { BikeDialog } from "@/components/bikes/parking-garage";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { bikesApi, trackingApi } from "@/lib/api";
import { apiErrorMessage, cn } from "@/lib/utils";

import { MapMarker, MARKER_COLORS, TrackerMap } from "./tracker-map";
import {
  accountLabel,
  FleetBike,
  FleetData,
  formatAgo,
  hasCoordinates,
  LOW_TRACKER_BATTERY,
} from "./tracking-format";

type Filter = "all" | "online" | "offline" | "rented" | "no_tracker";

const FILTERS: { value: Filter; label: string }[] = [
  { value: "all", label: "Все" },
  { value: "online", label: "На связи" },
  { value: "offline", label: "Нет связи" },
  { value: "rented", label: "В аренде" },
  { value: "no_tracker", label: "Без трекера" },
];

const REFRESH_MS = 30000;

function bikeColor(bike: FleetBike): string {
  if (!bike.position?.online) return MARKER_COLORS.offline;
  return bike.is_rented ? MARKER_COLORS.rented : MARKER_COLORS.online;
}

function matchesFilter(bike: FleetBike, filter: Filter): boolean {
  if (filter === "online") return Boolean(bike.position?.online);
  if (filter === "offline") return bike.tracker_id != null && !bike.position?.online;
  if (filter === "rented") return bike.is_rented;
  if (filter === "no_tracker") return bike.tracker_id == null;
  return true;
}

export function FleetMap() {
  const [data, setData] = useState<FleetData | null>(null);
  const [branches, setBranches] = useState<{ id: string; name: string }[]>([]);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const [search, setSearch] = useState("");
  const [focusId, setFocusId] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await trackingApi.fleet();
      setData(res.data as FleetData);
      setError("");
    } catch (err: any) {
      setError(apiErrorMessage(err, "Не удалось загрузить карту"));
    }
  }, []);

  useEffect(() => {
    load();
    bikesApi
      .branches()
      .then((res) => setBranches(res.data?.items ?? []))
      .catch(() => setBranches([]));
    const timer = setInterval(() => {
      if (!document.hidden) load();
    }, REFRESH_MS);
    return () => clearInterval(timer);
  }, [load]);

  const visible = useMemo(() => {
    const query = search.trim().toLowerCase();
    return (data?.bikes ?? []).filter(
      (bike) =>
        matchesFilter(bike, filter) &&
        (!query ||
          bike.model.toLowerCase().includes(query) ||
          (bike.frame_number ?? "").toLowerCase().includes(query))
    );
  }, [data, filter, search]);

  const markers = useMemo<MapMarker[]>(() => {
    const items: MapMarker[] = [];
    for (const bike of visible) {
      if (!hasCoordinates(bike.position)) continue;
      items.push({
        id: bike.id,
        latitude: bike.position.latitude,
        longitude: bike.position.longitude,
        label: bike.model,
        details: `${bike.frame_number ? `№ ${bike.frame_number} · ` : ""}${formatAgo(bike.position.gps_time)}`,
        color: bikeColor(bike),
      });
    }
    if (filter === "all") {
      for (const tracker of data?.unbound_trackers ?? []) {
        if (!hasCoordinates(tracker)) continue;
        items.push({
          id: `tracker-${tracker.tracker_id}`,
          latitude: tracker.latitude,
          longitude: tracker.longitude,
          label: tracker.title || `Трекер #${tracker.tracker_id}`,
          details: "Не привязан к байку",
          color: MARKER_COLORS.unbound,
        });
      }
    }
    return items;
  }, [visible, data, filter]);

  const bikes = data?.bikes ?? [];
  const onlineCount = bikes.filter((b) => b.position?.online).length;
  const noTrackerCount = bikes.filter((b) => b.tracker_id == null).length;
  const attention = bikes.filter(
    (b) =>
      b.position?.shock_alarm ||
      (b.position?.tracker_battery != null && b.position.tracker_battery < LOW_TRACKER_BATTERY)
  );
  const account = accountLabel(data?.account ?? null);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="secondary">Всего: {bikes.length}</Badge>
          <Badge>На связи: {onlineCount}</Badge>
          <Badge variant="secondary">Без трекера: {noTrackerCount}</Badge>
          {data && (
            <Badge variant={account.tone === "ok" ? "secondary" : "destructive"}>
              {account.text}
            </Badge>
          )}
        </div>
        <Button variant="outline" size="sm" onClick={load}>
          <RefreshCw className="mr-2 h-4 w-4" aria-hidden />
          Обновить
        </Button>
      </div>

      {error && <p className="rounded-md bg-red-50 p-3 text-sm text-red-600">{error}</p>}
      {data?.account.state !== "ok" && data?.account.message && (
        <p className="rounded-md bg-amber-50 p-3 text-sm text-amber-800">{data.account.message}</p>
      )}

      <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
        <TrackerMap
          markers={markers}
          focusId={focusId}
          onMarkerClick={(id) => {
            if (!id.startsWith("tracker-")) setSelectedId(id);
          }}
          className="h-[60vh] min-h-[360px] w-full"
        />

        <div className="flex max-h-[60vh] min-h-[360px] flex-col gap-2 rounded-lg border bg-white p-3">
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Поиск по модели или раме"
            className="h-9"
          />
          <div className="flex flex-wrap gap-1">
            {FILTERS.map((item) => (
              <Button
                key={item.value}
                size="sm"
                variant={filter === item.value ? "default" : "outline"}
                className="h-7 px-2 text-xs"
                onClick={() => setFilter(item.value)}
              >
                {item.label}
              </Button>
            ))}
          </div>

          <ul className="min-h-0 flex-1 space-y-1 overflow-y-auto">
            {visible.length === 0 && (
              <li className="py-6 text-center text-sm text-muted-foreground">
                {data ? "Нет байков" : "Загрузка…"}
              </li>
            )}
            {visible.map((bike) => (
              <li key={bike.id}>
                <button
                  type="button"
                  onClick={() => {
                    if (hasCoordinates(bike.position)) {
                      setFocusId(null);
                      setTimeout(() => setFocusId(bike.id));
                    } else {
                      setSelectedId(bike.id);
                    }
                  }}
                  onDoubleClick={() => setSelectedId(bike.id)}
                  className={cn(
                    "w-full rounded-md p-2 text-left transition-colors hover:bg-gray-50",
                    focusId === bike.id && "bg-gray-100"
                  )}
                >
                  <span className="flex items-center gap-2">
                    <span
                      aria-hidden
                      className="h-2.5 w-2.5 shrink-0 rounded-full"
                      style={{ background: bikeColor(bike) }}
                    />
                    <span className="truncate text-sm font-medium">{bike.model}</span>
                    {bike.position?.shock_alarm && (
                      <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-red-600" aria-label="Датчик удара" />
                    )}
                  </span>
                  <span className="mt-0.5 block truncate pl-[18px] text-xs text-muted-foreground">
                    {bike.tracker_id == null
                      ? "Трекер не привязан"
                      : `${formatAgo(bike.position?.reception_time ?? null)}${
                          bike.position?.tracker_battery != null
                            ? ` · батарея ${bike.position.tracker_battery}%`
                            : ""
                        }`}
                  </span>
                </button>
              </li>
            ))}
          </ul>
          {attention.length > 0 && (
            <p className="border-t pt-2 text-xs text-amber-700">
              Требуют внимания (удар или низкий заряд): {attention.length}
            </p>
          )}
        </div>
      </div>

      <BikeDialog
        bikeId={selectedId}
        open={selectedId !== null}
        onOpenChange={(v) => {
          if (!v) setSelectedId(null);
        }}
        branches={branches}
        onSaved={load}
      />
    </div>
  );
}
