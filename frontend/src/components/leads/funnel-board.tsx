"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  DndContext,
  DragOverlay,
  PointerSensor,
  KeyboardSensor,
  TouchSensor,
  useSensor,
  useSensors,
  closestCorners,
  type DragEndEvent,
  type DragStartEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  arrayMove,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { Phone, Mail, Plus, RefreshCw, GripVertical, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { leadsApi, customersApi } from "@/lib/api";
import {
  CustomerPicker,
  type PickedCustomer,
} from "@/components/customers/customer-picker";
import { LeadDetailDialog } from "@/components/leads/lead-detail-dialog";
import {
  ColumnVisibilityMenu,
  readHiddenStages,
} from "@/components/leads/column-visibility-menu";
import { useIsDesktop } from "@/hooks/use-media-query";
import { apiErrorMessage, cn } from "@/lib/utils";

interface Stage {
  id: string;
  name: string;
  order: number;
  color: string;
}

interface Lead {
  id: string;
  client_name: string | null;
  client_phone: string | null;
  client_email: string | null;
  status: string;
  stage_id: string | null;
  amount?: number | null;
  source?: { name: string; type: string } | null;
  messages?: { direction: string; created_at: string }[];
}

/** Последнее сообщение по сделке пришло от клиента — мы ещё не ответили. */
function isAwaitingReply(lead: Lead): boolean {
  const messages = lead.messages ?? [];
  if (messages.length === 0) return false;
  const last = messages.reduce((a, b) =>
    new Date(a.created_at).getTime() > new Date(b.created_at).getTime() ? a : b
  );
  return last.direction === "inbound";
}

interface Source {
  id: string;
  name: string;
  type: string;
}

const NO_SOURCE = "__none__";
const NO_STAGE = "__none__";

/* ------------------------------------------------------------------ */
/* Добавление лида                                                     */
/* ------------------------------------------------------------------ */

function AddLeadDialog({
  sources,
  onCreated,
}: {
  sources: Source[];
  onCreated: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [sourceId, setSourceId] = useState<string>(NO_SOURCE);
  const [customer, setCustomer] = useState<PickedCustomer | null>(null);
  const [typedName, setTypedName] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (sourceId === NO_SOURCE) {
      setError("Выберите источник");
      return;
    }
    setSaving(true);
    setError("");
    try {
      await leadsApi.create({
        source_id: sourceId,
        customer_id: customer?.id ?? null,
        client_name: customer?.full_name ?? typedName.trim() ?? undefined,
        client_phone: (customer?.phone || phone.trim()) || undefined,
        client_email: (customer?.email || email.trim()) || undefined,
        initial_message: message || undefined,
      });
      setOpen(false);
      setMessage("");
      onCreated();
    } catch (err: any) {
      setError(apiErrorMessage(err, "Не удалось создать лид"));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        setOpen(v);
        if (v) {
          setSourceId(sources.find((s) => s.type === "manual")?.id ?? NO_SOURCE);
          setPhone("");
          setEmail("");
          setError("");
        }
      }}
    >
      <DialogTrigger asChild>
        <Button>
          <Plus className="mr-2 h-4 w-4" aria-hidden />
          Добавить лид
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Новый лид</DialogTitle>
          <DialogDescription>Ручной ввод. Позже добавятся вебхуки.</DialogDescription>
        </DialogHeader>

        <form onSubmit={submit} className="space-y-3">
          <div className="space-y-1.5">
            <label className="text-sm font-medium" htmlFor="lead-source">
              Источник
            </label>
            <Select value={sourceId} onValueChange={setSourceId}>
              <SelectTrigger id="lead-source">
                <SelectValue placeholder="Выберите источник" />
              </SelectTrigger>
              <SelectContent>
                {sources.map((s) => (
                  <SelectItem key={s.id} value={s.id}>
                    {s.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <label className="text-sm font-medium" htmlFor="lead-customer">
              Клиент
            </label>
            <CustomerPicker
              value={customer}
              onChange={setCustomer}
              onTextChange={setTypedName}
              autoFocus
            />
            <p className="text-xs text-muted-foreground">
              Если клиента нет в базе — создайте его прямо отсюда
            </p>
          </div>

          {!customer && (
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <label className="text-sm font-medium" htmlFor="lead-phone">
                  Телефон
                </label>
                <Input
                  id="lead-phone"
                  type="tel"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  placeholder="+79001234567"
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-sm font-medium" htmlFor="lead-email">
                  Email
                </label>
                <Input
                  id="lead-email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="mail@example.com"
                />
              </div>
            </div>
          )}

          <div className="space-y-1.5">
            <label className="text-sm font-medium" htmlFor="lead-message">
              Сообщение
            </label>
            <Input
              id="lead-message"
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder="Хочу арендовать байк на выходные"
            />
          </div>

          {error && (
            <p className="rounded-md bg-red-50 p-2 text-sm text-red-600">{error}</p>
          )}

          <DialogFooter className="justify-end">
            <Button type="submit" disabled={saving}>
              {saving ? "Создаём…" : "Создать лид"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/* ------------------------------------------------------------------ */
/* Карточка лида                                                       */
/* ------------------------------------------------------------------ */

function LeadMeta({ lead }: { lead: Lead }) {
  return (
    <div className="mt-2 space-y-1 text-xs text-muted-foreground">
      {lead.client_phone && (
        <p className="flex items-center gap-1.5">
          <Phone className="h-3 w-3 shrink-0" aria-hidden />
          {lead.client_phone}
        </p>
      )}
      {lead.client_email && (
        <p className="flex items-center gap-1.5">
          <Mail className="h-3 w-3 shrink-0" aria-hidden />
          <span className="truncate">{lead.client_email}</span>
        </p>
      )}
      {lead.amount != null && (
        <p className="text-xs font-semibold text-foreground">
          {new Intl.NumberFormat("ru-RU", {
            style: "currency",
            currency: "RUB",
            maximumFractionDigits: 0,
          }).format(lead.amount)}
        </p>
      )}
    </div>
  );
}

function LeadCardBody({ lead }: { lead: Lead }) {
  const awaitingReply = isAwaitingReply(lead);
  return (
    <>
      <div className="flex items-start justify-between gap-2">
        <p className="text-sm font-medium leading-tight">
          {lead.client_name || "Без имени"}
        </p>
        {lead.source?.name && (
          <Badge variant="secondary" className="shrink-0 text-[11px]">
            {lead.source.name}
          </Badge>
        )}
      </div>

      {awaitingReply && (
        <span className="mt-1.5 inline-flex w-fit items-center rounded-full bg-orange-500 px-2 py-0.5 text-[11px] font-semibold text-white">
          Ждёт ответа
        </span>
      )}

      
      <LeadMeta lead={lead} />
    </>
  );
}

function DeleteButton({
  onClick,
  label,
}: {
  onClick: () => void;
  label: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md text-gray-300 transition-colors hover:bg-red-50 hover:text-red-600"
    >
      <Trash2 className="h-4 w-4" aria-hidden />
    </button>
  );
}

function SortableLeadCard({
  lead,
  onOpen,
  onDelete,
}: {
  lead: Lead;
  onOpen: (id: string) => void;
  onDelete: (lead: Lead) => void;
}) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: lead.id, data: { stageId: lead.stage_id } });

  return (
    <div
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={cn(
        "rounded-lg border bg-white shadow-sm transition-shadow hover:shadow-md",
        isDragging && "opacity-40"
      )}
    >
      <div className="flex items-start gap-1.5 p-3">
        <button
          type="button"
          className="mt-0.5 cursor-grab touch-none rounded p-0.5 text-gray-400 hover:bg-gray-100 hover:text-gray-600 active:cursor-grabbing"
          aria-label="Перетащить лид"
          {...attributes}
          {...listeners}
        >
          <GripVertical className="h-4 w-4" aria-hidden />
        </button>
        <div className="min-w-0 flex-1">
          <button
            type="button"
            onClick={() => onOpen(lead.id)}
            className="w-full cursor-pointer text-left"
            aria-label="Открыть карточку лида"
          >
            <LeadCardBody lead={lead} />
          </button>
        </div>
        <DeleteButton onClick={() => onDelete(lead)} label="Удалить лид" />
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Колонка этапа                                                       */
/* ------------------------------------------------------------------ */

function StageColumn({
  stage,
  leads,
  onOpen,
  onDelete,
}: {
  stage: Stage;
  leads: Lead[];
  onOpen: (id: string) => void;
  onDelete: (lead: Lead) => void;
}) {
  const { setNodeRef, isOver } = useSortable({
    id: stage.id,
    data: { type: "column", stageId: stage.id },
  });

  return (
    <div
      ref={setNodeRef}
      className={cn(
        "flex w-64 shrink-0 flex-col rounded-lg bg-gray-100 p-2 transition-colors",
        isOver && "bg-gray-200 ring-2 ring-primary/40"
      )}
    >
      <div className="mb-2 flex items-center justify-between gap-2 px-1">
        <div className="flex min-w-0 items-center gap-2">
          <span
            className="h-2.5 w-2.5 shrink-0 rounded-full"
            style={{ backgroundColor: stage.color }}
            aria-hidden
          />
          <span className="truncate text-sm font-semibold">{stage.name}</span>
        </div>
        <Badge variant="secondary" className="shrink-0">
          {leads.length}
        </Badge>
      </div>

      <SortableContext
        items={leads.map((l) => l.id)}
        strategy={verticalListSortingStrategy}
      >
        <div className="flex min-h-[80px] flex-col gap-2">
          {leads.length === 0 ? (
            <p className="rounded-lg border border-dashed p-3 text-center text-xs text-muted-foreground">
              Перетащите лид сюда
            </p>
          ) : (
            leads.map((lead) => (
              <SortableLeadCard
                key={lead.id}
                lead={lead}
                onOpen={onOpen}
                onDelete={onDelete}
              />
            ))
          )}
        </div>
      </SortableContext>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Мобильный вид: вкладки этапов + список                                */
/* ------------------------------------------------------------------ */

function MobileStageTabs({
  stages,
  counts,
  activeId,
  onSelect,
}: {
  stages: Stage[];
  counts: Record<string, number>;
  activeId: string | null;
  onSelect: (id: string) => void;
}) {
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});

  useEffect(() => {
    if (activeId && refs.current[activeId]) {
      refs.current[activeId]!.scrollIntoView({
        behavior: "smooth",
        block: "nearest",
        inline: "center",
      });
    }
  }, [activeId]);

  return (
    <div className="-mx-4 overflow-x-auto px-4">
      <div className="flex min-w-max gap-2 pb-1">
        {stages.map((stage) => {
          const active = stage.id === activeId;
          return (
            <button
              key={stage.id}
              ref={(el) => {
                refs.current[stage.id] = el;
              }}
              type="button"
              onClick={() => onSelect(stage.id)}
              aria-current={active ? "true" : undefined}
              className={cn(
                "flex shrink-0 items-center gap-2 rounded-full border px-3.5 py-2 text-sm font-medium transition-colors",
                active
                  ? "border-primary bg-primary text-primary-foreground"
                  : "border-gray-200 bg-white text-gray-700"
              )}
            >
              <span
                className="h-2 w-2 shrink-0 rounded-full"
                style={{ backgroundColor: active ? "#fff" : stage.color }}
                aria-hidden
              />
              {stage.name}
              <span
                className={cn(
                  "rounded-full px-1.5 py-0.5 text-[11px] font-semibold",
                  active ? "bg-white/20" : "bg-gray-100"
                )}
              >
                {counts[stage.id] ?? 0}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function MobileStageList({
  stage,
  leads,
  stages,
  onOpen,
  onDelete,
  onMove,
}: {
  stage: Stage | null;
  leads: Lead[];
  stages: Stage[];
  onOpen: (id: string) => void;
  onDelete: (lead: Lead) => void;
  onMove: (leadId: string, stageId: string) => void;
}) {
  if (!stage) {
    return (
      <p className="py-10 text-center text-sm text-muted-foreground">
        Все колонки скрыты — включите их в меню «Колонки»
      </p>
    );
  }

  return (
    <div className="space-y-2">
      {leads.length === 0 ? (
        <p className="rounded-lg border border-dashed bg-white p-8 text-center text-sm text-muted-foreground">
          В этой стадии пока пусто
        </p>
      ) : (
        leads.map((lead) => (
          <div key={lead.id} className="rounded-lg border bg-white p-3 shadow-sm">
            <div className="flex items-start gap-2">
              <button
                type="button"
                onClick={() => onOpen(lead.id)}
                className="min-w-0 flex-1 cursor-pointer text-left"
                aria-label="Открыть карточку лида"
              >
                <LeadCardBody lead={lead} />
              </button>
              <DeleteButton onClick={() => onDelete(lead)} label="Удалить лид" />
            </div>

            <Select
              value={lead.stage_id ?? ""}
              onValueChange={(v) => onMove(lead.id, v)}
            >
              <SelectTrigger className="mt-2 h-10 w-full text-sm">
                <SelectValue placeholder="Этап" />
              </SelectTrigger>
              <SelectContent>
                {stages.map((s) => (
                  <SelectItem key={s.id} value={s.id} className="text-sm">
                    {s.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        ))
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Воронка                                                             */
/* ------------------------------------------------------------------ */

export function FunnelBoard() {
  const [stages, setStages] = useState<Stage[]>([]);
  const [sources, setSources] = useState<Source[]>([]);
  const [columns, setColumns] = useState<Record<string, Lead[]>>({});
  const [leads, setLeads] = useState<Lead[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [selectedLeadId, setSelectedLeadId] = useState<string | null>(null);
  const [hiddenStages, setHiddenStages] = useState<string[]>([]);
  const [toDelete, setToDelete] = useState<Lead | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [mobileStageId, setMobileStageId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // Ссылка вида /orders?lead=<id> — так из сообщений открываются в карточку
  useEffect(() => {
    const lead = new URLSearchParams(window.location.search).get("lead");
    if (lead) setSelectedLeadId(lead);
  }, []);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(TouchSensor, {
      activationConstraint: { delay: 180, tolerance: 6 },
    }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
  );

  const group = useCallback(
    (items: Lead[]) => {
      const map: Record<string, Lead[]> = {};
      stages.forEach((s) => {
        map[s.id] = [];
      });
      map[NO_STAGE] = [];
      items.forEach((lead) => {
        const key = lead.stage_id ?? NO_STAGE;
        if (!map[key]) map[key] = [];
        map[key].push(lead);
      });
      return map;
    },
    [stages]
  );

  const load = useCallback(async () => {
    setError("");
    try {
      const [stagesRes, sourcesRes, leadsRes] = await Promise.all([
        leadsApi.stages(),
        leadsApi.sources(),
        leadsApi.list({ size: 100 }),
      ]);
      const loadedStages = stagesRes.data as Stage[];
      const loadedLeads = (leadsRes.data?.items ?? []) as Lead[];

      setStages(loadedStages);
      setSources(sourcesRes.data as Source[]);
      setLeads(loadedLeads);
      setColumns(group(loadedLeads));
    } catch (err: any) {
      setError(apiErrorMessage(err, "Не удалось загрузить воронку"));
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stages.length]);

  useEffect(() => {
    setHiddenStages(readHiddenStages());
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const findStage = (id: string): string | null => {
    const found = stages.find((s) => s.id === id);
    return found ? found.id : null;
  };

  const onDragStart = (event: DragStartEvent) => {
    setActiveId(String(event.active.id));
  };

  const onDragEnd = async (event: DragEndEvent) => {
    const { active, over } = event;
    setActiveId(null);
    if (!over) return;
    if (active.id === over.id) return;

    const leadId = String(active.id);

    // Приземлились в другую колонку
    const overIsColumn = stages.some((s) => s.id === String(over.id));
    let targetStageId: string;

    if (overIsColumn) {
      targetStageId = String(over.id);
    } else {
      const overLead = leads.find((l) => l.id === String(over.id));
      if (!overLead) return;
      targetStageId = overLead.stage_id ?? NO_STAGE;
    }

    const sourceStageId =
      leads.find((l) => l.id === leadId)?.stage_id ?? NO_STAGE;

    if (sourceStageId === targetStageId) {
      // Перестановка внутри одной колонки
      setColumns((prev) => {
        const list = prev[sourceStageId] ?? [];
        const oldIndex = list.findIndex((l) => l.id === leadId);
        const newIndex = list.findIndex((l) => l.id === String(over.id));
        if (oldIndex < 0 || newIndex < 0) return prev;
        return { ...prev, [sourceStageId]: arrayMove(list, oldIndex, newIndex) };
      });
      return;
    }

    const previous = columns;
    const next = { ...columns };
    next[sourceStageId] = (next[sourceStageId] ?? []).filter(
      (l) => l.id !== leadId
    );
    next[targetStageId] = [...(next[targetStageId] ?? [])];

    const movedLead = leads.find((l) => l.id === leadId);
    if (!movedLead) return;

    const overIndex = next[targetStageId].findIndex(
      (l) => l.id === String(over.id)
    );
    const insertAt = overIndex >= 0 ? overIndex : next[targetStageId].length;
    next[targetStageId].splice(insertAt, 0, movedLead);
    setColumns(next);

    const realStageId = findStage(targetStageId);
    if (!realStageId) {
      setColumns(previous);
      return;
    }

    try {
      await leadsApi.changeStage(leadId, realStageId);
      setLeads((prev) =>
        prev.map((l) => (l.id === leadId ? { ...l, stage_id: realStageId } : l))
      );
    } catch {
      setColumns(previous);
      load();
    }
  };

  const activeLead = useMemo(
    () => leads.find((l) => l.id === activeId) ?? null,
    [leads, activeId]
  );

  const visibleStages = useMemo(
    () => stages.filter((s) => !hiddenStages.includes(s.id)),
    [stages, hiddenStages]
  );

  const isDesktop = useIsDesktop();

  useEffect(() => {
    if (!isDesktop || !visibleStages.length) return;
    setMobileStageId((prev) =>
      prev && visibleStages.some((s) => s.id === prev)
        ? prev
        : visibleStages[0].id
    );
  }, [isDesktop, visibleStages]);

  const activeMobileStage =
    visibleStages.find((s) => s.id === mobileStageId) ?? visibleStages[0] ?? null;

  const confirmDelete = async () => {
    if (!toDelete) return;
    setDeleting(true);
    try {
      await leadsApi.remove(toDelete.id);
      setToDelete(null);
      await load();
    } catch (err: any) {
      setError(apiErrorMessage(err, "Не удалось скрыть лид"));
      setToDelete(null);
    } finally {
      setDeleting(false);
    }
  };

  const moveLead = async (leadId: string, stageId: string) => {
    if (stageId === NO_STAGE) return;
    try {
      await leadsApi.changeStage(leadId, stageId);
      setLeads((prev) =>
        prev.map((l) => (l.id === leadId ? { ...l, stage_id: stageId } : l))
      );
      setColumns((prev) => {
        const lead = leads.find((l) => l.id === leadId);
        if (!lead) return prev;
        const from = lead.stage_id ?? NO_STAGE;
        if (from === stageId) return prev;
        return {
          ...prev,
          [from]: (prev[from] ?? []).filter((l) => l.id !== leadId),
          [stageId]: [...(prev[stageId] ?? []), lead],
        };
      });
      } catch {
      setError("Не удалось изменить стадию");
      load();
    }
  };

  const counts = useMemo(() => {
    const acc: Record<string, number> = {};
    leads.forEach((l) => {
      const key = l.stage_id ?? NO_STAGE;
      acc[key] = (acc[key] ?? 0) + 1;
    });
    return acc;
  }, [leads]);

  if (loading) {
    return (
      <p className="py-8 text-center text-sm text-muted-foreground">
        Загружаем воронку…
      </p>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <h2 className="text-lg font-semibold">Воронка продаж</h2>
          <Badge variant="secondary">{leads.length}</Badge>
        </div>
        <div className="flex items-center gap-2">
          <ColumnVisibilityMenu
            stages={stages}
            hidden={hiddenStages}
            onChange={setHiddenStages}
          />
          <Button variant="outline" size="sm" onClick={load}>
            <RefreshCw className="mr-2 h-4 w-4" aria-hidden />
            Обновить
          </Button>
          <AddLeadDialog sources={sources} onCreated={load} />
        </div>
      </div>

      {error && (
        <p className="rounded-md bg-red-50 p-3 text-sm text-red-600">{error}</p>
      )}

      {isDesktop ? (
        <DndContext
          sensors={sensors}
          collisionDetection={closestCorners}
          onDragStart={onDragStart}
          onDragEnd={onDragEnd}
          onDragCancel={() => setActiveId(null)}
        >
          <div className="-mx-4 overflow-x-auto px-4 pb-2 lg:mx-0 lg:px-0">
            <div className="flex min-w-max gap-3">
              {visibleStages.map((stage) => (
                <StageColumn
                  key={stage.id}
                  stage={stage}
                  leads={columns[stage.id] ?? []}
                  onOpen={setSelectedLeadId}
                  onDelete={setToDelete}
                />
              ))}
            </div>
          </div>

          <DragOverlay>
            {activeLead ? (
              <div className="rounded-lg border bg-white p-3 shadow-lg">
                <LeadCardBody lead={activeLead} />
              </div>
            ) : null}
          </DragOverlay>
        </DndContext>
      ) : (
        <div className="space-y-3">
          <MobileStageTabs
            stages={visibleStages}
            counts={counts}
            activeId={activeMobileStage?.id ?? null}
            onSelect={setMobileStageId}
          />
          <MobileStageList
            stage={activeMobileStage}
            leads={
              activeMobileStage ? columns[activeMobileStage.id] ?? [] : []
            }
            stages={visibleStages}
            onOpen={setSelectedLeadId}
            onDelete={setToDelete}
            onMove={moveLead}
          />
        </div>
      )}

      <p className="text-xs text-muted-foreground">
        {isDesktop
          ? "Клик по карточке открывает сделку. Перетащите за левый край (⋮⋮) в другую колонку, чтобы изменить этап."
          : "Коснитесь карточки, чтобы открыть сделку. Стадию меняйте списком в карточке."}
      </p>

      <LeadDetailDialog
        leadId={selectedLeadId}
        open={selectedLeadId !== null}
        onOpenChange={(v) => {
          if (!v) {
            setSelectedLeadId(null);
            const url = new URL(window.location.href);
            if (url.searchParams.has("lead")) {
              url.searchParams.delete("lead");
              window.history.replaceState({}, "", url.toString());
            }
          }
        }}
        stages={stages}
        onSaved={load}
      />

      <Dialog open={toDelete !== null} onOpenChange={(v) => !v && setToDelete(null)}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Скрыть лид?</DialogTitle>
            <DialogDescription>
              {toDelete?.client_name || "Без имени"}
              {toDelete?.client_phone ? ` · ${toDelete.client_phone}` : ""}. Лид уйдёт
              из воронки и перестанет учитываться в статистике, но история,
              комментарии и сообщения сохранятся.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setToDelete(null)} disabled={deleting}>
              Отмена
            </Button>
            <Button variant="destructive" onClick={confirmDelete} disabled={deleting}>
              {deleting ? "Скрываем…" : "Скрыть"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
