"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, Plus, Trash2, X, Zap } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "@/hooks/use-toast";

import { api } from "@/lib/api";
import { apiErrorMessage, cn } from "@/lib/utils";

interface CannedReply {
  id: string;
  title: string;
  text: string;
  shortcut: string | null;
}

/**
 * Меню предзаписанных сообщений в форме ответа.
 * Клик по шаблону вставляет его текст в поле ввода.
 */
export function CannedRepliesMenu({
  onPick,
}: {
  onPick: (text: string) => void;
}) {
  const queryClient = useQueryClient();
  const wrapRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [manage, setManage] = useState(false);
  const [search, setSearch] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["canned-replies"],
    queryFn: async () => {
      const { data } = await api.get<{ items: CannedReply[] }>("/canned-replies");
      return data.items;
    },
    enabled: open,
  });

  useEffect(() => {
    if (!open) return;
    const onClickOutside = (event: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, [open]);

  const resetForm = () => {
    setEditingId(null);
    setTitle("");
    setText("");
  };

  const save = useMutation({
    mutationFn: async () => {
      if (editingId) {
        await api.patch(`/canned-replies/${editingId}`, { title, text });
      } else {
        await api.post("/canned-replies", { title, text });
      }
    },
    onSuccess: () => {
      toast({ title: editingId ? "Шаблон обновлён" : "Шаблон добавлен" });
      resetForm();
      queryClient.invalidateQueries({ queryKey: ["canned-replies"] });
    },
    onError: (error: { response?: { data?: { detail?: unknown } } }) => {
      toast({
        title: "Не удалось сохранить",
        description: apiErrorMessage(error, "Ошибка сохранения"),
      });
    },
  });

  const remove = useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/canned-replies/${id}`);
    },
    onSuccess: () => {
      toast({ title: "Шаблон удалён" });
      if (editingId) resetForm();
      queryClient.invalidateQueries({ queryKey: ["canned-replies"] });
    },
    onError: (error: { response?: { data?: { detail?: unknown } } }) => {
      toast({
        title: "Не удалось удалить",
        description: apiErrorMessage(error, "Ошибка удаления"),
      });
    },
  });

  const items = (data || []).filter((item) => {
    if (!search.trim()) return true;
    const needle = search.trim().toLowerCase();
    return (
      item.title.toLowerCase().includes(needle) ||
      item.text.toLowerCase().includes(needle)
    );
  });

  const startEdit = (item: CannedReply) => {
    setManage(true);
    setEditingId(item.id);
    setTitle(item.title);
    setText(item.text);
  };

  const canSave = Boolean(title.trim() && text.trim()) && !save.isPending;

  return (
    <div ref={wrapRef} className="relative shrink-0">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        title="Предзаписанные сообщения"
        className={cn(
          "flex h-[38px] w-[38px] items-center justify-center rounded-md border transition-colors",
          open
            ? "border-primary bg-primary/10 text-primary"
            : "bg-background text-muted-foreground hover:text-foreground"
        )}
      >
        <Zap className="h-4 w-4" />
      </button>

      {open && (
        <div className="absolute bottom-full left-0 z-30 mb-2 w-80 rounded-lg border bg-background shadow-lg">
          <div className="flex items-center gap-1.5 border-b p-2">
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Поиск шаблона…"
              className="min-w-0 flex-1 rounded-md border bg-background px-2 py-1.5 text-xs outline-none focus:ring-2 focus:ring-ring"
            />
            <button
              type="button"
              onClick={() => {
                setManage((v) => !v);
                resetForm();
              }}
              title={manage ? "Вернуться к выбору" : "Редактировать шаблоны"}
              className={cn(
                "flex h-7 w-7 items-center justify-center rounded border",
                manage
                  ? "border-primary text-primary"
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              <Pencil className="h-3.5 w-3.5" />
            </button>
            {!manage && (
              <button
                type="button"
                onClick={() => setManage(true)}
                title="Добавить шаблон"
                className="flex h-7 w-7 items-center justify-center rounded border text-muted-foreground hover:text-foreground"
              >
                <Plus className="h-3.5 w-3.5" />
              </button>
            )}
            <button
              type="button"
              onClick={() => setOpen(false)}
              title="Закрыть"
              className="flex h-7 w-7 items-center justify-center rounded text-muted-foreground hover:text-foreground"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>

          {manage && (
            <div className="space-y-2 border-b p-2">
              <input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Название (например: Приветствие)"
                className="w-full rounded-md border bg-background px-2 py-1.5 text-xs outline-none focus:ring-2 focus:ring-ring"
              />
              <textarea
                value={text}
                onChange={(e) => setText(e.target.value)}
                rows={4}
                placeholder="Текст сообщения…"
                className="w-full resize-y rounded-md border bg-background px-2 py-1.5 text-xs outline-none focus:ring-2 focus:ring-ring"
              />
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => save.mutate()}
                  disabled={!canSave}
                  className="rounded-md bg-primary px-3 py-1.5 text-xs text-primary-foreground disabled:opacity-50"
                >
                  {save.isPending ? "…" : editingId ? "Обновить" : "Добавить"}
                </button>
                <button
                  type="button"
                  onClick={resetForm}
                  className="rounded-md border px-3 py-1.5 text-xs"
                >
                  Отмена
                </button>
              </div>
            </div>
          )}

          <div className="max-h-64 overflow-y-auto p-1">
            {isLoading && (
              <p className="p-2 text-xs text-muted-foreground">Загрузка…</p>
            )}
            {!isLoading && items.length === 0 && (
              <p className="p-2 text-xs text-muted-foreground">
                {manage
                  ? "Шаблонов пока нет — добавьте первый"
                  : "Шаблонов пока нет. Нажмите «+», чтобы добавить"}
              </p>
            )}
            {items.map((item) =>
              manage ? (
                <div
                  key={item.id}
                  className="flex items-center justify-between gap-2 rounded-md px-2 py-1.5 hover:bg-muted"
                >
                  <div className="min-w-0">
                    <p className="truncate text-xs font-medium">{item.title}</p>
                    <p className="truncate text-[11px] text-muted-foreground">
                      {item.text}
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-1">
                    <button
                      type="button"
                      onClick={() => startEdit(item)}
                      title="Изменить"
                      className="flex h-6 w-6 items-center justify-center rounded text-muted-foreground hover:bg-background hover:text-foreground"
                    >
                      <Pencil className="h-3.5 w-3.5" />
                    </button>
                    <button
                      type="button"
                      onClick={() => remove.mutate(item.id)}
                      disabled={remove.isPending}
                      title="Удалить"
                      className="flex h-6 w-6 items-center justify-center rounded text-muted-foreground hover:bg-red-50 hover:text-red-600"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>
              ) : (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => {
                    onPick(item.text);
                    setOpen(false);
                  }}
                  className="block w-full rounded-md px-2 py-1.5 text-left hover:bg-muted"
                  title={item.shortcut ? `Команда ${item.shortcut}` : item.title}
                >
                  <span className="block text-xs font-medium">{item.title}</span>
                  <span className="mt-0.5 line-clamp-2 block text-[11px] text-muted-foreground">
                    {item.text}
                  </span>
                </button>
              )
            )}
          </div>
        </div>
      )}
    </div>
  );
}
