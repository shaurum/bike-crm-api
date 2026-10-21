"use client";

import { isValidElement, type ReactNode } from "react";

import { Toast, ToastClose, ToastDescription, ToastProvider, ToastTitle, ToastViewport } from "@/components/ui/toast";
import { useToast } from "@/hooks/use-toast";

/**
 * Текст для тоста из любого значения.
 *
 * detail от FastAPI может быть объектом (дубль контакта) или массивом
 * ошибок валидации — рендерить их как React-детей нельзя, React падает
 * с «Objects are not valid as a React child». Здесь всё приводится
 * к строке.
 */
function safeNode(value: unknown): ReactNode {
  if (value === null || value === undefined || value === false) return null;
  if (typeof value === "string" || typeof value === "number") return value;
  if (isValidElement(value)) return value;
  if (Array.isArray(value)) {
    const parts = value
      .map(safeNode)
      .filter((part) => part !== null && part !== undefined && part !== false);
    return parts.length > 0 ? parts : null;
  }
  if (typeof value === "object") {
    const record = value as Record<string, unknown>;
    if (typeof record.detail === "string") return record.detail;
    try {
      return JSON.stringify(value);
    } catch {
      return "Ошибка";
    }
  }
  return String(value);
}

export function Toaster() {
  const { toasts } = useToast();

  return (
    <ToastProvider>
      {toasts.map(function ({ id, title, description, action, ...props }) {
        const safeTitle = safeNode(title);
        const safeDescription = safeNode(description);
        return (
          <Toast key={id} {...props}>
            <div className="grid gap-1">
              {safeTitle && <ToastTitle>{safeTitle}</ToastTitle>}
              {safeDescription && <ToastDescription>{safeDescription}</ToastDescription>}
            </div>
            {action}
            <ToastClose />
          </Toast>
        );
      })}
      <ToastViewport />
    </ToastProvider>
  );
}
