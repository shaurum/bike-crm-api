"use client";

import { CheckCircle2, Loader2, XCircle } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";

type Phase = "working" | "done" | "failed";

export default function AvitoCallbackPage() {
  const router = useRouter();
  const [phase, setPhase] = useState<Phase>("working");
  const [message, setMessage] = useState("");

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const code = params.get("code");
    const errorText =
      params.get("error_description") || params.get("error") || "";

    if (errorText) {
      setPhase("failed");
      setMessage(errorText);
      return;
    }
    if (!code) {
      setPhase("failed");
      setMessage("В адресе нет кода авторизации");
      return;
    }

    let cancelled = false;

    (async () => {
      try {
        await api.post("/settings/integrations/avito/callback", { code });
        if (!cancelled) setPhase("done");
      } catch (error) {
        const detail = (
          error as { response?: { data?: { detail?: string } } }
        )?.response?.data?.detail;
        if (!cancelled) {
          setPhase("failed");
          setMessage(detail || "Не удалось сохранить доступ к Авито");
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="mx-auto flex w-full max-w-lg flex-col items-center gap-4 rounded-lg border p-8 text-center">
      {phase === "working" && (
        <>
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
          <p className="text-sm font-medium">Подключаем Авито…</p>
          <p className="text-xs text-muted-foreground">
            Обмениваем код авторизации на токен и запоминаем аккаунт.
          </p>
        </>
      )}

      {phase === "done" && (
        <>
          <CheckCircle2 className="h-8 w-8 text-green-600" />
          <p className="text-sm font-medium">Авито подключён</p>
          <p className="text-xs text-muted-foreground">
            Входящие сообщения начнут появляться в разделе «Сообщения» в течение
            минуты.
          </p>
          <div className="flex gap-2">
            <button
              onClick={() => router.replace("/settings?tab=integrations")}
              className="rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
            >
              Вернуться в настройки
            </button>
            <button
              onClick={() => router.replace("/messages")}
              className="rounded-md border px-3 py-2 text-sm font-medium transition-colors hover:bg-muted"
            >
              Открыть сообщения
            </button>
          </div>
        </>
      )}

      {phase === "failed" && (
        <>
          <XCircle className="h-8 w-8 text-red-600" />
          <p className="text-sm font-medium">Не получилось подключить Авито</p>
          <p className="text-xs text-red-600">{message}</p>
          <button
            onClick={() => router.replace("/settings?tab=integrations")}
            className="rounded-md border px-3 py-2 text-sm font-medium transition-colors hover:bg-muted"
          >
            Вернуться в настройки
          </button>
        </>
      )}
    </div>
  );
}
