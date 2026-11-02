"use client";

import { useEffect, useRef } from "react";
import type { LayerGroup, Map as LeafletMap } from "leaflet";
import "leaflet/dist/leaflet.css";

import { cn } from "@/lib/utils";

export interface MapMarker {
  id: string;
  latitude: number;
  longitude: number;
  label: string;
  details?: string;
  color: string;
}

export const MARKER_COLORS = {
  online: "#16a34a",
  rented: "#2563eb",
  offline: "#9ca3af",
  unbound: "#f59e0b",
};

// Центр по умолчанию, пока на карте нет ни одного трекера
const DEFAULT_CENTER: [number, number] = [55.75, 37.62];

export function TrackerMap({
  markers,
  track,
  focusId,
  onMarkerClick,
  className,
}: {
  markers: MapMarker[];
  track?: [number, number][];
  focusId?: string | null;
  onMarkerClick?: (id: string) => void;
  className?: string;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<LeafletMap | null>(null);
  const layerRef = useRef<LayerGroup | null>(null);
  const leafletRef = useRef<typeof import("leaflet") | null>(null);
  const fittedRef = useRef(false);
  const clickRef = useRef(onMarkerClick);
  clickRef.current = onMarkerClick;
  const dataRef = useRef({ markers, track });
  dataRef.current = { markers, track };

  const draw = () => {
    const L = leafletRef.current;
    const map = mapRef.current;
    const layer = layerRef.current;
    if (!L || !map || !layer) return;
    const { markers: items, track: line } = dataRef.current;

    layer.clearLayers();
    if (line && line.length > 1) {
      L.polyline(line, { color: "#2563eb", weight: 3, opacity: 0.7 }).addTo(layer);
    }
    for (const item of items) {
      const dot = document.createElement("div");
      dot.style.cssText = `width:16px;height:16px;border-radius:50%;border:2px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.45);background:${item.color}`;

      // Подписи приходят от внешнего сервиса, поэтому только textContent
      const tooltip = document.createElement("div");
      const title = document.createElement("strong");
      title.textContent = item.label;
      tooltip.appendChild(title);
      if (item.details) {
        const details = document.createElement("div");
        details.textContent = item.details;
        tooltip.appendChild(details);
      }

      const marker = L.marker([item.latitude, item.longitude], {
        icon: L.divIcon({ html: dot, className: "", iconSize: [16, 16], iconAnchor: [8, 8] }),
        title: item.label,
      }).addTo(layer);
      marker.bindTooltip(tooltip, { direction: "top", offset: [0, -8] });
      marker.on("click", () => clickRef.current?.(item.id));
    }

    // Подгоняем вид один раз, чтобы автообновление не сбрасывало масштаб пользователя
    const bounds: [number, number][] = [
      ...items.map((m): [number, number] => [m.latitude, m.longitude]),
      ...(line ?? []),
    ];
    if (bounds.length > 0 && !fittedRef.current) {
      map.fitBounds(bounds, { padding: [32, 32], maxZoom: 15 });
      fittedRef.current = true;
    }
  };

  useEffect(() => {
    let cancelled = false;
    let observer: ResizeObserver | null = null;

    // Leaflet обращается к window при импорте, поэтому грузим его только в браузере
    import("leaflet").then((L) => {
      if (cancelled || !containerRef.current) return;
      leafletRef.current = L;
      const map = L.map(containerRef.current).setView(DEFAULT_CENTER, 10);
      L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19,
        attribution: "&copy; OpenStreetMap",
      }).addTo(map);
      layerRef.current = L.layerGroup().addTo(map);
      mapRef.current = map;

      // Диалог открывается с анимацией: без этого карта считает размер неверно
      observer = new ResizeObserver(() => map.invalidateSize());
      observer.observe(containerRef.current);
      draw();
    });

    return () => {
      cancelled = true;
      observer?.disconnect();
      mapRef.current?.remove();
      mapRef.current = null;
      layerRef.current = null;
      fittedRef.current = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    draw();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [markers, track]);

  useEffect(() => {
    if (track && track.length > 1) fittedRef.current = false;
    draw();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [track]);

  useEffect(() => {
    const target = markers.find((m) => m.id === focusId);
    if (target && mapRef.current) {
      mapRef.current.setView([target.latitude, target.longitude], Math.max(mapRef.current.getZoom(), 15));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusId]);

  // isolate: панели Leaflet с z-index до 1000 не перекрывают шапку и диалоги
  return <div ref={containerRef} className={cn("isolate rounded-lg border bg-gray-100", className)} />;
}
