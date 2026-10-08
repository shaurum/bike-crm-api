"use client";

import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronUp } from "lucide-react";

import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

interface ServiceStatus {
  key: string;
  label: string;
  status: "ok" | "warn" | "down" | "off";
  detail: string | null;
  last_ok_at: string | null;
}

interface HealthPayload {
  services: ServiceStatus[];
  checked_at: string;
}

const DOT: Record<string, string> = {
  ok: "bg-green-500",
  warn: "bg-amber-500",
  down: "bg-red-500",
  off: "bg-gray-300",
};

const STATUS_WORD: Record<string, string> = {
  warn: "внимание",
  down: "недоступен",
  off: "выключен",
};

function agoLabel(iso: string | null): string {
  if (!iso) return "нет данных";
  const min = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (min < 1) return "только что";
  if (min < 60) return `${min} мин назад`;
  const h = Math.floor(min / 60);
  if (h < 24) return `${h} ч назад`;
  return `${Math.floor(h / 24)} дн назад`;
}

/** Индикаторы здоровья сервисов: зелёная точка, при проблемах — красная с деталями. */
export function HealthStatus() {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const apiDownSince = useRef<number | null>(null);
  const [apiDownLabel, setApiDownLabel] = useState<string | null>(null);

  // Закрытие popover: клик мимо и Escape
  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  const { data, error } = useQuery<HealthPayload>({
    queryKey: ["health-services"],
    queryFn: async () => {
      const { data } = await api.get("/health/services");
      return data;
    },
    refetchInterval: 30000,
    retry: false,
  });

  useEffect(() => {
    if (!error) {
      apiDownSince.current = null;
      setApiDownLabel(null);
      return;
    }
    if (!apiDownSince.current) apiDownSince.current = Date.now();
    const update = () => {
      const min = Math.round(
        (Date.now() - (apiDownSince.current || Date.now())) / 60000
      );
      setApiDownLabel(
        min < 1 ? "API CRM недоступен" : `API CRM недоступен ~${min} мин`
      );
    };
    update();
    const timer = setInterval(update, 30000);
    return () => clearInterval(timer);
  }, [error]);

  const services = data?.services ?? [];
  const problems = services.filter(
    (s) => s.status === "down" || s.status === "warn"
  );
  const hasDown = problems.some((s) => s.status === "down");
  const healthy = !error && problems.length === 0;
  const summary = error
    ? apiDownLabel ?? "API CRM недоступен"
    : problems.length === 0
      ? "Сервисы в норме"
      : hasDown
        ? `Проблемы: ${problems.length}`
        : `Внимание: ${problems.length}`;

  return (
    <div className="relative" ref={rootRef}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={cn(
          "flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-xs font-medium transition-colors",
          healthy
            ? "text-gray-600 hover:bg-gray-100"
            : hasDown || error
              ? "bg-red-50 text-red-600 hover:bg-red-100"
              : "bg-amber-50 text-amber-700 hover:bg-amber-100"
        )}
        title="Здоровье сервисов"
      >
        <span
          className={cn(
            "h-2.5 w-2.5 shrink-0 rounded-full",
            healthy
              ? "bg-green-500"
              : hasDown || error
                ? "animate-pulse bg-red-500"
                : "bg-amber-500"
          )}
        />
        <span className="flex-1 truncate">{summary}</span>
        <ChevronUp
          className={cn("h-3.5 w-3.5 transition-transform", open && "rotate-180")}
        />
      </button>

      {open && (
        <div className="absolute bottom-full left-0 z-40 mb-1 w-72 rounded-lg border bg-white p-2 shadow-lg">
          <p className="px-1 pb-1 text-[11px] font-semibold uppercase text-gray-400">
            Сервисы
          </p>
          <ul className="space-y-0.5">
            {error && (
              <li className="flex items-center gap-2 rounded px-1 py-1.5 text-xs text-red-600">
                <span className="h-2 w-2 shrink-0 rounded-full bg-red-500" />
                API CRM — {apiDownLabel ?? "недоступен"}
              </li>
            )}
            {services.map((s) => (
              <li
                key={s.key}
                className="flex items-start gap-2 rounded px-1 py-1 hover:bg-gray-50"
              >
                <span
                  className={cn("mt-1 h-2 w-2 shrink-0 rounded-full", DOT[s.status])}
                />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-xs font-medium text-gray-800">
                    {s.label}
                  </p>
                  <p className="truncate text-[11px] text-gray-500">
                    {s.status === "ok"
                      ? s.detail || "в норме"
                      : s.detail
                        ? s.detail
                        : `${STATUS_WORD[s.status] || s.status} · был ок ${agoLabel(s.last_ok_at)}`}
                  </p>
                </div>
              </li>
            ))}
            {services.length === 0 && !error && (
              <li className="px-1 py-1 text-xs text-gray-400">Загрузка…</li>
            )}
          </ul>
          <p className="px-1 pt-1.5 text-[10px] text-gray-400">
            Обновляется каждые 30 секунд
          </p>
        </div>
      )}
    </div>
  );
}
