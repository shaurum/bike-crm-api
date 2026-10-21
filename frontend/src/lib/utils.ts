import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Человекочитаемый текст ошибки из ответа API.
 *
 * FastAPI умеет отдавать detail не строкой: объект-дубль контакта
 * (code/scope/…) или массив ошибок валидации. Рендерить такие значения
 * в React нельзя — получаем «Objects are not valid as a React child».
 */
export function apiErrorMessage(err: unknown, fallback: string): string {
  const detail = (
    err as { response?: { data?: { detail?: unknown } } }
  )?.response?.data?.detail;

  if (typeof detail === "string" && detail) return detail;

  if (Array.isArray(detail)) {
    const first = detail[0];
    if (typeof first === "string" && first) return first;
    if (first && typeof first === "object" && typeof (first as { msg?: unknown }).msg === "string") {
      return (first as { msg: string }).msg;
    }
    return fallback;
  }

  if (detail && typeof detail === "object") {
    const d = detail as Record<string, unknown>;
    if (d.code === "duplicate") {
      const value = typeof d.value === "string" ? d.value : "";
      const name = typeof d.customer_name === "string" ? d.customer_name : "";
      if (d.scope === "same") return `Контакт «${value}» уже есть у этого клиента`;
      return `Контакт «${value}» уже используется${name ? ` у «${name}»` : ""}`;
    }
    if (typeof d.detail === "string" && d.detail) return d.detail;
    try {
      return JSON.stringify(detail);
    } catch {
      return fallback;
    }
  }

  return fallback;
}

export function formatDate(date: string | Date, format: string = "dd.MM.yyyy"): string {
  const d = new Date(date);
  const day = String(d.getDate()).padStart(2, "0");
  const month = String(d.getMonth() + 1).padStart(2, "0");
  const year = d.getFullYear();
  const hours = String(d.getHours()).padStart(2, "0");
  const minutes = String(d.getMinutes()).padStart(2, "0");

  return format
    .replace("dd", day)
    .replace("MM", month)
    .replace("yyyy", String(year))
    .replace("HH", hours)
    .replace("mm", minutes);
}

export function formatCurrency(amount: number): string {
  return new Intl.NumberFormat("ru-RU", {
    style: "currency",
    currency: "RUB",
    minimumFractionDigits: 0,
  }).format(amount);
}

export function getStatusColor(status: string): string {
  const colors: Record<string, string> = {
    new: "bg-blue-100 text-blue-800",
    contacted: "bg-yellow-100 text-yellow-800",
    qualified: "bg-purple-100 text-purple-800",
    booking: "bg-indigo-100 text-indigo-800",
    won: "bg-green-100 text-green-800",
    lost: "bg-red-100 text-red-800",
    pending: "bg-yellow-100 text-yellow-800",
    confirmed: "bg-blue-100 text-blue-800",
    active: "bg-green-100 text-green-800",
    completed: "bg-gray-100 text-gray-800",
    cancelled: "bg-red-100 text-red-800",
    no_show: "bg-orange-100 text-orange-800",
    available: "bg-green-100 text-green-800",
    reserved: "bg-yellow-100 text-yellow-800",
    rented: "bg-blue-100 text-blue-800",
    maintenance: "bg-red-100 text-red-800",
    charging: "bg-purple-100 text-purple-800",
    relocation: "bg-orange-100 text-orange-800",
    todo: "bg-gray-100 text-gray-800",
    in_progress: "bg-blue-100 text-blue-800",
    done: "bg-green-100 text-green-800",
  };
  return colors[status] || "bg-gray-100 text-gray-800";
}

export function getStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    new: "Новый",
    contacted: "Связались",
    qualified: "Квалифицирован",
    booking: "Бронирование",
    won: "Выиграли",
    lost: "Потеряли",
    pending: "Ожидает",
    confirmed: "Подтверждена",
    active: "Активна",
    completed: "Завершена",
    cancelled: "Отменена",
    no_show: "Не явился",
    available: "Доступен",
    reserved: "Зарезервирован",
    rented: "В аренде",
    maintenance: "На обслуживании",
    charging: "Заряжается",
    relocation: "Перемещение",
    todo: "К выполнению",
    in_progress: "В работе",
    done: "Выполнено",
  };
  return labels[status] || status;
}