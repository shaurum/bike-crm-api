"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  LayoutGrid,
  List,
  Pencil,
  Plus,
  Search,
  Trash2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { tasksApi, usersApi } from "@/lib/api";
import { useAuthStore } from "@/lib/store";
import { toast } from "@/hooks/use-toast";
import { cn } from "@/lib/utils";

interface Task {
  id: string;
  type: string;
  title: string;
  description: string | null;
  status: string;
  priority: string;
  due_at: string | null;
  assignee_id: string | null;
  created_by_id: string | null;
  created_at: string;
  updated_at: string;
}

interface UserOption {
  id: string;
  full_name?: string | null;
  email?: string | null;
}

const STATUS_LABELS: Record<string, string> = {
  todo: "К выполнению",
  in_progress: "В работе",
  done: "Готово",
  cancelled: "Отменено",
};

const TYPE_LABELS: Record<string, string> = {
  call: "Звонок",
  meeting: "Встреча",
  contract: "Договор",
  maintenance: "Обслуживание",
  handover: "Выдача",
  return: "Возврат",
  custom: "Другое",
};

const PRIORITY_LABELS: Record<string, string> = {
  low: "Низкий",
  normal: "Обычный",
  high: "Высокий",
};

const PRIORITY_CLASS: Record<string, string> = {
  low: "text-blue-500",
  normal: "text-muted-foreground",
  high: "text-red-500",
};

const BOARD_STATUSES = ["todo", "in_progress", "done", "cancelled"] as const;

function errText(err: unknown, fallback: string): string {
  const detail = (err as { response?: { data?: { detail?: unknown } } })
    ?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  return fallback;
}

function pad(n: number): string {
  return String(n).padStart(2, "0");
}

function dueInfo(dueAt: string | null) {
  if (!dueAt) return null;
  const d = new Date(dueAt);
  const now = new Date();
  const startOf = (x: Date) =>
    new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const dayDiff = Math.round((startOf(d) - startOf(now)) / 86400000);
  const overdue = d.getTime() < now.getTime() && dayDiff < 0;
  const time = `${pad(d.getHours())}:${pad(d.getMinutes())}`;
  const date = `${pad(d.getDate())}.${pad(d.getMonth() + 1)}`;
  let label: string;
  if (dayDiff === 0) label = time;
  else if (dayDiff === 1) label = `завтра ${time}`;
  else if (dayDiff === -1) label = `вчера ${time}`;
  else label = `${date} ${time}`;
  return { overdue, today: dayDiff === 0, label };
}

function isFinished(task: Task): boolean {
  return task.status === "done" || task.status === "cancelled";
}

interface FormState {
  id?: string;
  title: string;
  type: string;
  priority: string;
  status: string;
  due_date: string;
  due_time: string;
  description: string;
  assignee_id: string;
}

function emptyForm(assigneeId: string): FormState {
  return {
    title: "",
    type: "custom",
    priority: "normal",
    status: "todo",
    due_date: "",
    due_time: "",
    description: "",
    assignee_id: assigneeId,
  };
}

function taskToForm(task: Task): FormState {
  let dueDate = "";
  let dueTime = "";
  if (task.due_at) {
    const d = new Date(task.due_at);
    dueDate = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
    dueTime = `${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }
  return {
    id: task.id,
    title: task.title,
    type: task.type,
    priority: task.priority,
    status: task.status,
    due_date: dueDate,
    due_time: dueTime,
    description: task.description || "",
    assignee_id: task.assignee_id || "",
  };
}

export default function TasksPage() {
  const queryClient = useQueryClient();
  const me = useAuthStore((state) => state.user);

  const [view, setView] = useState<"list" | "board">("list");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [assigneeFilter, setAssigneeFilter] = useState("all");
  const [overdueOnly, setOverdueOnly] = useState(false);
  const [form, setForm] = useState<FormState | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Task | null>(null);
  const [dragOver, setDragOver] = useState<string | null>(null);

  const { data: tasksData, isLoading } = useQuery({
    queryKey: ["tasks", search, statusFilter, assigneeFilter, overdueOnly],
    queryFn: async () => {
      const { data } = await tasksApi.list({
        size: 500,
        q: search || undefined,
        status: statusFilter === "all" ? undefined : statusFilter,
        assignee_id:
          assigneeFilter === "all"
            ? undefined
            : assigneeFilter === "me"
              ? me?.id
              : assigneeFilter,
        overdue: overdueOnly || undefined,
      });
      return data as { items: Task[] };
    },
  });

  const { data: users } = useQuery({
    queryKey: ["users", "list"],
    queryFn: async () => {
      const { data } = await usersApi.list();
      return data as UserOption[];
    },
  });

  const tasks = useMemo(() => tasksData?.items ?? [], [tasksData]);

  const nameById = useMemo(() => {
    const map = new Map<string, string>();
    for (const u of (users ?? []) as UserOption[]) {
      map.set(u.id, u.full_name || u.email || "—");
    }
    return map;
  }, [users]);

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["tasks"] });
  };

  const onError = (err: unknown, title: string) =>
    toast({ title, description: errText(err, "Ошибка") });

  const save = useMutation({
    mutationFn: async () => {
      if (!form) return;
      const due_at = form.due_date
        ? new Date(`${form.due_date}T${form.due_time || "09:00"}`).toISOString()
        : null;
      const payload: Record<string, unknown> = {
        type: form.type,
        title: form.title,
        description: form.description || null,
        priority: form.priority,
        due_at,
        assignee_id: form.assignee_id || null,
      };
      if (form.id) {
        await tasksApi.update(form.id, { ...payload, status: form.status });
      } else {
        await tasksApi.create(payload);
      }
    },
    onSuccess: () => {
      toast({ title: form?.id ? "Задача обновлена" : "Задача создана" });
      setForm(null);
      invalidate();
    },
    onError: (err) => onError(err, "Не удалось сохранить"),
  });

  const toggleStatus = useMutation({
    mutationFn: async (task: Task) => {
      const next = task.status === "done" ? "todo" : "done";
      await tasksApi.updateStatus(task.id, next);
    },
    onSuccess: () => invalidate(),
    onError: (err) => onError(err, "Не удалось изменить статус"),
  });

  const move = useMutation({
    mutationFn: async ({ id, status }: { id: string; status: string }) => {
      await tasksApi.updateStatus(id, status);
    },
    onSuccess: () => invalidate(),
    onError: (err) => onError(err, "Не удалось переместить"),
  });

  const remove = useMutation({
    mutationFn: async () => {
      if (!deleteTarget) return;
      await tasksApi.remove(deleteTarget.id);
    },
    onSuccess: () => {
      toast({ title: "Задача удалена" });
      setDeleteTarget(null);
      invalidate();
    },
    onError: (err) => onError(err, "Не удалось удалить"),
  });

  const openCreate = () => setForm(emptyForm(me?.id ?? ""));
  const openEdit = (task: Task) => setForm(taskToForm(task));

  const groups = useMemo(() => {
    const now = new Date();
    const buckets: Record<string, Task[]> = {
      overdue: [],
      today: [],
      upcoming: [],
      nodue: [],
      finished: [],
    };
    for (const task of tasks) {
      if (isFinished(task)) {
        buckets.finished.push(task);
        continue;
      }
      const info = dueInfo(task.due_at);
      if (!info) buckets.nodue.push(task);
      else if (info.overdue) buckets.overdue.push(task);
      else if (info.today) buckets.today.push(task);
      else buckets.upcoming.push(task);
    }
    const dueSort = (a: Task, b: Task) =>
      new Date(a.due_at!).getTime() - new Date(b.due_at!).getTime();
    buckets.overdue.sort(dueSort);
    buckets.today.sort(dueSort);
    buckets.upcoming.sort(dueSort);
    return [
      { key: "overdue", label: "Просроченные", items: buckets.overdue },
      { key: "today", label: "Сегодня", items: buckets.today },
      { key: "upcoming", label: "Далее", items: buckets.upcoming },
      { key: "nodue", label: "Без срока", items: buckets.nodue },
      { key: "finished", label: "Завершённые", items: buckets.finished },
    ].filter((g) => g.items.length > 0);
  }, [tasks]);

  const totalActive = useMemo(
    () => tasks.filter((t) => !isFinished(t)).length,
    [tasks]
  );

  const renderRow = (task: Task) => {
    const info = dueInfo(task.due_at);
    const done = task.status === "done";
    return (
      <div
        key={task.id}
        className={cn(
          "group flex items-center gap-3 border-b px-4 py-2.5 hover:bg-muted/40",
          done && "opacity-60"
        )}
      >
        <input
          type="checkbox"
          checked={done}
          onChange={() => toggleStatus.mutate(task)}
          className="h-4 w-4 shrink-0 cursor-pointer accent-primary"
          title={done ? "Вернуть в работу" : "Отметить выполненной"}
        />
        <button
          type="button"
          onClick={() => openEdit(task)}
          className="min-w-0 flex-1 text-left"
        >
          <div className="flex flex-wrap items-center gap-2">
            <span
              className={cn(
                "truncate text-sm",
                done && "line-through",
                info?.overdue && "font-semibold text-red-600 dark:text-red-400"
              )}
            >
              {task.title}
            </span>
            <span
              className={cn(
                "shrink-0 text-[11px]",
                PRIORITY_CLASS[task.priority] || "text-muted-foreground"
              )}
              title={`Приоритет: ${PRIORITY_LABELS[task.priority] || task.priority}`}
            >
              ●
            </span>
            <Badge variant="outline" className="shrink-0 text-[11px]">
              {TYPE_LABELS[task.type] || task.type}
            </Badge>
            {task.status !== "todo" && task.status !== "done" && (
              <Badge variant="secondary" className="shrink-0 text-[11px]">
                {STATUS_LABELS[task.status] || task.status}
              </Badge>
            )}
            {info && (
              <span
                className={cn(
                  "shrink-0 text-[11px]",
                  info.overdue
                    ? "font-semibold text-red-600 dark:text-red-400"
                    : "text-muted-foreground"
                )}
              >
                {info.label}
              </span>
            )}
          </div>
        </button>
        <span className="hidden shrink-0 text-xs text-muted-foreground sm:block">
          {task.assignee_id
            ? nameById.get(task.assignee_id) || "—"
            : me?.id === task.assignee_id
              ? "я"
              : "—"}
        </span>
        <div className="flex shrink-0 items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
          <button
            type="button"
            onClick={() => openEdit(task)}
            className="flex h-7 w-7 items-center justify-center rounded text-muted-foreground hover:bg-muted"
            title="Редактировать"
          >
            <Pencil className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            onClick={() => setDeleteTarget(task)}
            className="flex h-7 w-7 items-center justify-center rounded text-muted-foreground hover:bg-red-50 hover:text-red-600"
            title="Удалить"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    );
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-2xl font-bold">Задачи</h1>
          <p className="text-sm text-muted-foreground">
            {totalActive} активных
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex rounded-md border">
            <button
              type="button"
              onClick={() => setView("list")}
              className={cn(
                "flex h-9 w-9 items-center justify-center",
                view === "list" ? "bg-muted" : "text-muted-foreground"
              )}
              title="Список"
            >
              <List className="h-4 w-4" />
            </button>
            <button
              type="button"
              onClick={() => setView("board")}
              className={cn(
                "flex h-9 w-9 items-center justify-center",
                view === "board" ? "bg-muted" : "text-muted-foreground"
              )}
              title="Доска"
            >
              <LayoutGrid className="h-4 w-4" />
            </button>
          </div>
          <Button onClick={openCreate}>
            <Plus className="mr-1.5 h-4 w-4" aria-hidden />
            Новая задача
          </Button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <div className="relative">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Поиск по названию…"
            className="w-56 pl-8"
          />
        </div>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="h-9 rounded-md border border-input bg-background px-2 text-sm"
        >
          <option value="all">Все статусы</option>
          {BOARD_STATUSES.map((s) => (
            <option key={s} value={s}>
              {STATUS_LABELS[s]}
            </option>
          ))}
        </select>
        <select
          value={assigneeFilter}
          onChange={(e) => setAssigneeFilter(e.target.value)}
          className="h-9 rounded-md border border-input bg-background px-2 text-sm"
        >
          <option value="all">Все исполнители</option>
          <option value="me">Мои</option>
          {((users ?? []) as UserOption[]).map((u) => (
            <option key={u.id} value={u.id}>
              {u.full_name || u.email}
            </option>
          ))}
        </select>
        <label className="flex cursor-pointer items-center gap-1.5 text-sm text-muted-foreground">
          <input
            type="checkbox"
            checked={overdueOnly}
            onChange={(e) => setOverdueOnly(e.target.checked)}
            className="h-4 w-4 accent-red-600"
          />
          Только просроченные
        </label>
      </div>

      {isLoading && (
        <p className="py-8 text-center text-sm text-muted-foreground">
          Загрузка…
        </p>
      )}

      {!isLoading && tasks.length === 0 && (
        <div className="rounded-lg border border-dashed p-12 text-center">
          <p className="text-sm text-muted-foreground">Задач нет</p>
          <Button variant="outline" className="mt-3" onClick={openCreate}>
            <Plus className="mr-1.5 h-4 w-4" aria-hidden />
            Создать задачу
          </Button>
        </div>
      )}

      {view === "list" &&
        !isLoading &&
        groups.map((group) => (
          <div key={group.key} className="rounded-lg border">
            <div
              className={cn(
                "border-b px-4 py-2 text-xs font-semibold uppercase tracking-wide",
                group.key === "overdue"
                  ? "bg-red-50 text-red-700 dark:bg-red-950/30 dark:text-red-400"
                  : "bg-muted/50 text-muted-foreground"
              )}
            >
              {group.label} · {group.items.length}
            </div>
            <div>{group.items.map(renderRow)}</div>
          </div>
        ))}

      {view === "board" && !isLoading && tasks.length > 0 && (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          {BOARD_STATUSES.map((status) => {
            const items = tasks.filter((t) => t.status === status);
            return (
              <div
                key={status}
                onDragOver={(e) => {
                  e.preventDefault();
                  setDragOver(status);
                }}
                onDragLeave={() => setDragOver(null)}
                onDrop={(e) => {
                  e.preventDefault();
                  setDragOver(null);
                  const id = e.dataTransfer.getData("text/task-id");
                  if (id) move.mutate({ id, status });
                }}
                className={cn(
                  "flex min-h-40 flex-col rounded-lg border bg-muted/30",
                  dragOver === status && "border-primary ring-2 ring-primary/30"
                )}
              >
                <div className="flex items-center justify-between border-b px-3 py-2">
                  <span className="text-xs font-semibold uppercase text-muted-foreground">
                    {STATUS_LABELS[status]}
                  </span>
                  <span className="rounded bg-muted px-1.5 text-[11px] text-muted-foreground">
                    {items.length}
                  </span>
                </div>
                <div className="flex-1 space-y-2 p-2">
                  {items.map((task) => {
                    const info = dueInfo(task.due_at);
                    return (
                      <div
                        key={task.id}
                        draggable
                        onDragStart={(e) =>
                          e.dataTransfer.setData("text/task-id", task.id)
                        }
                        onClick={() => openEdit(task)}
                        className={cn(
                          "cursor-grab rounded-md border bg-background p-2 shadow-sm hover:border-primary/50 active:cursor-grabbing",
                          isFinished(task) && "opacity-60"
                        )}
                      >
                        <p className="text-sm font-medium">{task.title}</p>
                        <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                          <span
                            className={cn(
                              "text-[11px]",
                              PRIORITY_CLASS[task.priority] ||
                                "text-muted-foreground"
                            )}
                          >
                            ●
                          </span>
                          <Badge variant="outline" className="text-[10px]">
                            {TYPE_LABELS[task.type] || task.type}
                          </Badge>
                          {info && (
                            <span
                              className={cn(
                                "text-[11px]",
                                info.overdue
                                  ? "font-semibold text-red-600 dark:text-red-400"
                                  : "text-muted-foreground"
                              )}
                            >
                              {info.label}
                            </span>
                          )}
                        </div>
                        {task.assignee_id && (
                          <p className="mt-1 text-[11px] text-muted-foreground">
                            {nameById.get(task.assignee_id) || "—"}
                          </p>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Создание / редактирование */}
      <Dialog open={Boolean(form)} onOpenChange={(v) => !v && setForm(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>
              {form?.id ? "Редактировать задачу" : "Новая задача"}
            </DialogTitle>
          </DialogHeader>
          {form && (
            <div className="space-y-3">
              <Input
                value={form.title}
                onChange={(e) => setForm({ ...form, title: e.target.value })}
                placeholder="Название *"
                autoFocus
              />
              <div className="grid grid-cols-2 gap-2">
                <select
                  value={form.type}
                  onChange={(e) => setForm({ ...form, type: e.target.value })}
                  className="h-9 rounded-md border border-input bg-background px-2 text-sm"
                >
                  {Object.entries(TYPE_LABELS).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
                <select
                  value={form.priority}
                  onChange={(e) =>
                    setForm({ ...form, priority: e.target.value })
                  }
                  className="h-9 rounded-md border border-input bg-background px-2 text-sm"
                >
                  {Object.entries(PRIORITY_LABELS).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="grid grid-cols-3 gap-2">
                <input
                  type="date"
                  value={form.due_date}
                  onChange={(e) =>
                    setForm({ ...form, due_date: e.target.value })
                  }
                  className="h-9 rounded-md border border-input bg-background px-2 text-sm"
                />
                <input
                  type="time"
                  value={form.due_time}
                  onChange={(e) =>
                    setForm({ ...form, due_time: e.target.value })
                  }
                  className="h-9 rounded-md border border-input bg-background px-2 text-sm"
                />
                <select
                  value={form.status}
                  onChange={(e) => setForm({ ...form, status: e.target.value })}
                  className="h-9 rounded-md border border-input bg-background px-2 text-sm"
                >
                  {Object.entries(STATUS_LABELS).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </div>
              <select
                value={form.assignee_id}
                onChange={(e) =>
                  setForm({ ...form, assignee_id: e.target.value })
                }
                className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
              >
                <option value="">Исполнитель не назначен</option>
                {((users ?? []) as UserOption[]).map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.full_name || u.email}
                  </option>
                ))}
              </select>
              <textarea
                value={form.description}
                onChange={(e) =>
                  setForm({ ...form, description: e.target.value })
                }
                placeholder="Описание"
                rows={3}
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              />
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setForm(null)}>
              Отмена
            </Button>
            <Button
              onClick={() => save.mutate()}
              disabled={save.isPending || !form?.title.trim()}
            >
              {save.isPending ? "…" : "Сохранить"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Удаление */}
      <Dialog
        open={Boolean(deleteTarget)}
        onOpenChange={(v) => !v && setDeleteTarget(null)}
      >
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Удалить задачу</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">{deleteTarget?.title}</p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteTarget(null)}>
              Отмена
            </Button>
            <Button
              variant="destructive"
              onClick={() => remove.mutate()}
              disabled={remove.isPending}
            >
              {remove.isPending ? "…" : "Удалить"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
