"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { BatteryCharging, Clock, Gauge, MapPin, Route, Satellite, Zap } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { bikesApi, trackingApi } from "@/lib/api";
import { apiErrorMessage } from "@/lib/utils";

import { MARKER_COLORS, TrackerMap } from "./tracker-map";
import {
  accountLabel,
  AccountState,
  formatAgo,
  hasCoordinates,
  LOW_TRACKER_BATTERY,
  TrackerPosition,
} from "./tracking-format";

interface TrackerOption {
  tracker_id: number;
  title: string | null;
  note: string | null;
  bike_id: string | null;
}

const NO_TRACKER = "none";
const REFRESH_MS = 30000;

function Metric({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof MapPin;
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-md bg-gray-50 p-2">
      <p className="flex items-center gap-1 text-xs text-muted-foreground">
        <Icon className="h-3 w-3" aria-hidden />
        {label}
      </p>
      <p className="mt-0.5 text-sm font-medium">{value}</p>
    </div>
  );
}

export function BikeTrackingPanel({
  bikeId,
  trackerId,
  model,
  onBound,
}: {
  bikeId: string;
  trackerId: number | null;
  model: string;
  onBound: (data: unknown) => void;
}) {
  const [account, setAccount] = useState<AccountState | null>(null);
  const [position, setPosition] = useState<TrackerPosition | null>(null);
  const [options, setOptions] = useState<TrackerOption[]>([]);
  const [track, setTrack] = useState<[number, number][] | null>(null);
  const [trackInfo, setTrackInfo] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const loadPosition = useCallback(async () => {
    try {
      const res = await trackingApi.bike(bikeId);
      setAccount(res.data.account);
      setPosition(res.data.position ?? null);
    } catch (err: any) {
      setError(apiErrorMessage(err, "Не удалось получить положение байка"));
    }
  }, [bikeId]);

  useEffect(() => {
    setPosition(null);
    setTrack(null);
    setTrackInfo("");
    loadPosition();
    if (trackerId == null) return;
    const timer = setInterval(loadPosition, REFRESH_MS);
    return () => clearInterval(timer);
  }, [loadPosition, trackerId]);

  useEffect(() => {
    trackingApi
      .trackers()
      .then((res) => {
        setOptions(res.data.items ?? []);
      })
      .catch(() => setOptions([]));
  }, [trackerId]);

  const bind = async (value: string) => {
    setBusy(true);
    setError("");
    try {
      const res = await bikesApi.update(bikeId, {
        tracker_id: value === NO_TRACKER ? null : Number(value),
      });
      onBound(res.data);
    } catch (err: any) {
      setError(apiErrorMessage(err, "Не удалось привязать трекер"));
    } finally {
      setBusy(false);
    }
  };

  const toggleTrack = async () => {
    if (track) {
      setTrack(null);
      setTrackInfo("");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const res = await trackingApi.track(bikeId, 24);
      const points: { latitude: number; longitude: number }[] = res.data.points ?? [];
      setTrack(points.map((p) => [p.latitude, p.longitude]));
      setTrackInfo(
        points.length === 0
          ? "За сутки нет точек"
          : `Точек за сутки: ${points.length}` +
              (res.data.dropped ? `, отброшено сбойных: ${res.data.dropped}` : "")
      );
    } catch (err: any) {
      setError(apiErrorMessage(err, "Не удалось загрузить маршрут"));
    } finally {
      setBusy(false);
    }
  };

  const markers = useMemo(
    () =>
      hasCoordinates(position)
        ? [
            {
              id: bikeId,
              latitude: position.latitude,
              longitude: position.longitude,
              label: model,
              details: formatAgo(position.gps_time),
              color: position.online ? MARKER_COLORS.online : MARKER_COLORS.offline,
            },
          ]
        : [],
    [bikeId, model, position]
  );

  const accountInfo = accountLabel(account);
  const lowBattery =
    position?.tracker_battery != null && position.tracker_battery < LOW_TRACKER_BATTERY;

  return (
    <div className="space-y-3 rounded-lg border p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="flex items-center gap-1.5 text-sm font-semibold">
          <MapPin className="h-4 w-4 text-muted-foreground" aria-hidden />
          Местоположение
        </p>
        {position && (
          <Badge variant={position.online ? "default" : "secondary"}>
            {position.online ? "На связи" : "Нет связи"}
          </Badge>
        )}
      </div>

      {/* Состояние GDEGAZEL видно в статусе системы, здесь — только когда что-то не так */}
      {account && account.state !== "ok" && (
        <p className="rounded-md bg-amber-50 p-2 text-sm text-amber-800">{accountInfo.text}</p>
      )}

      <div className="space-y-1.5">
        <label className="text-xs font-medium">GPS-трекер</label>
        <Select
          value={trackerId != null ? String(trackerId) : NO_TRACKER}
          onValueChange={bind}
          disabled={busy}
        >
          <SelectTrigger>
            <SelectValue placeholder="Не привязан" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={NO_TRACKER}>Не привязан</SelectItem>
            {trackerId != null && !options.some((o) => o.tracker_id === trackerId) && (
              <SelectItem value={String(trackerId)}>#{trackerId}</SelectItem>
            )}
            {options
              .filter((o) => !o.bike_id || o.bike_id === bikeId)
              .map((o) => (
                <SelectItem key={o.tracker_id} value={String(o.tracker_id)}>
                  {o.title || `#${o.tracker_id}`}
                  {o.note ? ` · ${o.note}` : ""}
                </SelectItem>
              ))}
          </SelectContent>
        </Select>
      </div>

      {error && <p className="rounded-md bg-red-50 p-2 text-sm text-red-600">{error}</p>}

      {trackerId != null && (
        <>
          {markers.length > 0 ? (
            <TrackerMap markers={markers} track={track ?? undefined} className="h-64 w-full" />
          ) : (
            <p className="rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground">
              Трекер ещё не передал координаты
            </p>
          )}

          {position && (
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              <Metric icon={Clock} label="Координаты" value={formatAgo(position.gps_time)} />
              <Metric
                icon={Gauge}
                label="Скорость"
                value={position.speed != null ? `${position.speed} км/ч` : "—"}
              />
              <Metric
                icon={BatteryCharging}
                label={lowBattery ? "Батарея трекера: низкий заряд" : "Батарея трекера"}
                value={position.tracker_battery != null ? `${position.tracker_battery}%` : "—"}
              />
              <Metric
                icon={Zap}
                label="Напряжение байка"
                value={position.external_voltage != null ? `${position.external_voltage} В` : "—"}
              />
              <Metric
                icon={Satellite}
                label="Спутники"
                value={position.satellites != null ? String(position.satellites) : "—"}
              />
              <Metric icon={Clock} label="Связь" value={formatAgo(position.reception_time)} />
            </div>
          )}

          {position?.shock_alarm && (
            <p className="rounded-md bg-red-50 p-2 text-sm text-red-600">
              Сработал датчик удара
            </p>
          )}

          <div className="flex flex-wrap items-center gap-3">
            <Button variant="outline" size="sm" disabled={busy} onClick={toggleTrack}>
              <Route className="mr-2 h-4 w-4" aria-hidden />
              {track ? "Скрыть маршрут" : "Маршрут за сутки"}
            </Button>
            {trackInfo && <span className="text-xs text-muted-foreground">{trackInfo}</span>}
          </div>
        </>
      )}
    </div>
  );
}
