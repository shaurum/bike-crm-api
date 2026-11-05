"use client";

import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound, RotateCcw, Save } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toast } from "@/hooks/use-toast";
import { runtimeSettingsApi } from "@/lib/api";
import { apiErrorMessage } from "@/lib/utils";

interface RuntimeKey {
  name: string;
  label: string;
  group: string;
  help: string;
  secret: boolean;
  url: boolean;
  source: "settings" | "env" | "default" | "none";
  value: string | null;
}

const SOURCE: Record<RuntimeKey["source"], { text: string; variant: "default" | "secondary" | "destructive" | "outline" }> = {
  settings: { text: "Задан в настройках", variant: "default" },
  env: { text: "Из .env", variant: "secondary" },
  default: { text: "Ключ по умолчанию, замените", variant: "destructive" },
  none: { text: "Не задан", variant: "outline" },
};

export default function KeysTab() {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<Record<string, string>>({});

  const { data, isLoading, error } = useQuery({
    queryKey: ["runtime-settings"],
    queryFn: async () => (await runtimeSettingsApi.get()).data.keys as RuntimeKey[],
  });

  // Несекретные значения показываем как есть, секреты всегда начинаются с пустого поля
  useEffect(() => {
    if (!data) return;
    setDraft(Object.fromEntries(data.map((key) => [key.name, key.secret ? "" : key.value ?? ""])));
  }, [data]);

  const groups = useMemo(() => {
    const result = new Map<string, RuntimeKey[]>();
    for (const key of data ?? []) {
      result.set(key.group, [...(result.get(key.group) ?? []), key]);
    }
    return Array.from(result.entries());
  }, [data]);

  const changed = useMemo(() => {
    const values: Record<string, string> = {};
    for (const key of data ?? []) {
      const next = (draft[key.name] ?? "").trim();
      if (key.secret ? next !== "" : next !== (key.value ?? "")) values[key.name] = next;
    }
    return values;
  }, [data, draft]);

  const onSaved = (title: string) => {
    toast({ title });
    queryClient.invalidateQueries({ queryKey: ["runtime-settings"] });
    queryClient.invalidateQueries({ queryKey: ["health-services"] });
  };

  const save = useMutation({
    // Пустой адрес — вернуться к .env; пустой секрет сюда не попадает, он значит «не менять»
    mutationFn: async () =>
      runtimeSettingsApi.update({
        values: Object.fromEntries(Object.entries(changed).filter(([, value]) => value)),
        clear: Object.keys(changed).filter((name) => !changed[name]),
      }),
    onSuccess: () => onSaved("Ключи сохранены"),
    onError: (err) =>
      toast({ title: "Не удалось сохранить", description: apiErrorMessage(err, "Ошибка") }),
  });

  const clear = useMutation({
    mutationFn: async (name: string) => runtimeSettingsApi.update({ clear: [name] }),
    onSuccess: () => onSaved("Значение из настроек удалено, работает .env"),
    onError: (err) =>
      toast({ title: "Не удалось сбросить", description: apiErrorMessage(err, "Ошибка") }),
  });

  if (isLoading) return <p className="text-sm text-muted-foreground">Загрузка…</p>;
  if (error)
    return (
      <p className="rounded-md bg-red-50 p-3 text-sm text-red-600">
        {apiErrorMessage(error, "Не удалось загрузить ключи")}
      </p>
    );

  const hasChanges = Object.keys(changed).length > 0;

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h2 className="flex items-center gap-2 font-semibold">
          <KeyRound className="h-4 w-4" aria-hidden />
          Ключи и токены
        </h2>
        <p className="text-sm text-muted-foreground">
          Значение из настроек главнее .env. Сохранённые токены не показываются: чтобы
          заменить, введите новый. Другие процессы CRM подхватывают изменения в течение
          30 секунд. Почта и Авито настраиваются во вкладке «Интеграции»; пароли базы и
          ключи подписи остаются в .env.
        </p>
      </div>

      {groups.map(([group, keys]) => (
        <section key={group} className="space-y-4 rounded-lg border p-4">
          <h3 className="text-sm font-semibold">{group}</h3>
          {keys.map((key) => {
            const source = SOURCE[key.source];
            return (
              <div key={key.name} className="space-y-1.5">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <label htmlFor={`key-${key.name}`} className="text-sm font-medium">
                    {key.label}
                  </label>
                  <Badge variant={source.variant}>{source.text}</Badge>
                </div>
                <div className="flex flex-wrap gap-2 sm:flex-nowrap">
                  <Input
                    id={`key-${key.name}`}
                    type={key.secret ? "password" : "text"}
                    autoComplete={key.secret ? "new-password" : "off"}
                    spellCheck={false}
                    value={draft[key.name] ?? ""}
                    placeholder={
                      key.secret
                        ? key.source === "none"
                          ? "Введите значение"
                          : "Сохранён, введите новый, чтобы заменить"
                        : "Не задан"
                    }
                    onChange={(e) => setDraft((d) => ({ ...d, [key.name]: e.target.value }))}
                  />
                  {key.source === "settings" && (
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="h-10 shrink-0"
                      disabled={clear.isPending}
                      onClick={() => clear.mutate(key.name)}
                    >
                      <RotateCcw className="mr-2 h-4 w-4" aria-hidden />
                      Вернуть .env
                    </Button>
                  )}
                </div>
                <p className="text-xs text-muted-foreground">
                  {key.help}
                  <span className="ml-1 font-mono text-[11px] opacity-70">{key.name}</span>
                </p>
              </div>
            );
          })}
        </section>
      ))}

      <div className="flex justify-end">
        <Button onClick={() => save.mutate()} disabled={!hasChanges || save.isPending}>
          <Save className="mr-2 h-4 w-4" aria-hidden />
          {save.isPending ? "Сохранение…" : "Сохранить"}
        </Button>
      </div>
    </div>
  );
}
