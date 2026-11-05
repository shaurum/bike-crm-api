export interface AccountState {
  state: string;
  message?: string | null;
}

export interface TrackerPosition {
  tracker_id: number | null;
  title: string | null;
  note: string | null;
  latitude: number | null;
  longitude: number | null;
  speed: number | null;
  satellites: number | null;
  ignition: boolean | null;
  moving: boolean | null;
  shock_alarm: boolean | null;
  engine_locked: boolean | null;
  external_power: boolean | null;
  external_voltage: number | null;
  tracker_battery: number | null;
  gps_time: string | null;
  reception_time: string | null;
  online: boolean;
}

export interface FleetBike {
  id: string;
  model: string;
  frame_number: string | null;
  status: string;
  is_rented: boolean;
  tracker_id: number | null;
  position: TrackerPosition | null;
}

export interface FleetData {
  account: AccountState;
  bikes: FleetBike[];
  unbound_trackers: TrackerPosition[];
}

export const LOW_TRACKER_BATTERY = 20;

export function accountLabel(account: AccountState | null): {
  text: string;
  tone: "ok" | "warn" | "error";
} {
  switch (account?.state) {
    case "ok":
      // Сумму баланса API не отдаёт: блокировка видна только после 7 дней минуса
      return { text: "GDEGAZEL: доступ активен", tone: "ok" };
    case "payment_required":
      return { text: "Нужно пополнить баланс GDEGAZEL", tone: "error" };
    case "invalid_token":
      return { text: "Неверный токен GDEGAZEL", tone: "error" };
    case "not_configured":
      return { text: "Токен GDEGAZEL не задан", tone: "warn" };
    default:
      return { text: "GDEGAZEL недоступен", tone: "warn" };
  }
}

export function formatAgo(iso: string | null, now = Date.now()): string {
  if (!iso) return "нет данных";
  const minutes = Math.floor((now - new Date(iso).getTime()) / 60000);
  if (Number.isNaN(minutes)) return "нет данных";
  if (minutes < 1) return "только что";
  if (minutes < 60) return `${minutes} мин назад`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} ч назад`;
  return `${Math.floor(hours / 24)} дн назад`;
}

export function hasCoordinates(
  position: TrackerPosition | null | undefined
): position is TrackerPosition & { latitude: number; longitude: number } {
  return position?.latitude != null && position?.longitude != null;
}
