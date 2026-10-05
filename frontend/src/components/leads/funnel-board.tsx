"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Phone, Mail, Plus, RefreshCw } from "lucide-react";

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
import { leadsApi } from "@/lib/api";
import { cn } from "@/lib/utils";

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
  source?: { name: string; type: string } | null;
}

interface Source {
  id: string;
  name: string;
  type: string;
}

const NO_SOURCE = "__none__";

function AddLeadDialog({
  sources,
  onCreated,
}: {
  sources: Source[];
  onCreated: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [sourceId, setSourceId] = useState<string>(NO_SOURCE);
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const reset = () => {
    setName("");
    setPhone("");
    setEmail("");
    setMessage("");
    setError("");
    setSourceId(sources.find((s) => s.type === "manual")?.id ?? NO_SOURCE);
  };

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
        client_name: name || undefined,
        client_phone: phone || undefined,
        client_email: email || undefined,
        initial_message: message || undefined,
      });
      setOpen(false);
      reset();
      onCreated();
    } catch (err: any) {
      setError(err.response?.data?.detail || "Не удалось создать лид");
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
            <label className="text-sm font-medium" htmlFor="lead-name">
              Имя
            </label>
            <Input
              id="lead-name"
              name="name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Иван Петров"
            />
          </div>

          <div className="space-y-1.5">
            <label className="text-sm font-medium" htmlFor="lead-phone">
              Телефон
            </label>
            <Input
              id="lead-phone"
              name="tel"
              type="tel"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="+7 999 123-45-67"
            />
          </div>

          <div className="space-y-1.5">
            <label className="text-sm font-medium" htmlFor="lead-email">
              Email
            </label>
            <Input
              id="lead-email"
              name="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="ivan@example.com"
            />
          </div>

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

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>
              Отмена
            </Button>
            <Button type="submit" disabled={saving}>
              {saving ? "Создаём…" : "Создать лид"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function LeadCard({
  lead,
  stages,
  onMoved,
}: {
  lead: Lead;
  stages: Stage[];
  onMoved: () => void;
}) {
  const [busy, setBusy] = useState(false);

  const move = async (stageId: string) => {
    if (!stageId || stageId === lead.stage_id) return;
    setBusy(true);
    try {
      await leadsApi.changeStage(lead.id, stageId);
      onMoved();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="rounded-lg border bg-white p-3 shadow-sm">
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

      <div className="mt-2 space-y-1 text-xs text-muted-foreground">
        {lead.client_phone && (
          <p className="flex items-center gap-1.5">
            <Phone className="h-3 w-3" aria-hidden />
            {lead.client_phone}
          </p>
        )}
        {lead.client_email && (
          <p className="flex items-center gap-1.5 truncate">
            <Mail className="h-3 w-3" aria-hidden />
            <span className="truncate">{lead.client_email}</span>
          </p>
        )}
      </div>

      <Select value={lead.stage_id ?? ""} onValueChange={move} disabled={busy}>
        <SelectTrigger className="mt-2 h-8 w-full text-xs">
          <SelectValue placeholder="Этап" />
        </SelectTrigger>
        <SelectContent>
          {stages.map((s) => (
            <SelectItem key={s.id} value={s.id} className="text-xs">
              {s.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

export function FunnelBoard() {
  const [stages, setStages] = useState<Stage[]>([]);
  const [sources, setSources] = useState<Source[]>([]);
  const [leads, setLeads] = useState<Lead[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      const [stagesRes, sourcesRes, leadsRes] = await Promise.all([
        leadsApi.stages(),
        leadsApi.sources(),
        leadsApi.list({ size: 100 }),
      ]);
      setStages(stagesRes.data as Stage[]);
      setSources(sourcesRes.data as Source[]);
      setLeads((leadsRes.data?.items ?? []) as Lead[]);
    } catch (err: any) {
      setError(err.response?.data?.detail || "Не удалось загрузить воронку");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const grouped = useMemo(() => {
    const map = new Map<string, Lead[]>();
    stages.forEach((s) => map.set(s.id, []));
    leads.forEach((lead) => {
      const key = lead.stage_id ?? "";
      if (!map.has(key)) map.set(key, []);
      map.get(key)!.push(lead);
    });
    return map;
  }, [stages, leads]);

  const unassigned = leads.filter((l) => !l.stage_id);

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

      {unassigned.length > 0 && (
        <div className="rounded-lg border border-dashed border-amber-400 bg-amber-50 p-3">
          <p className="text-sm font-medium text-amber-900">
            Без этапа: {unassigned.length}
          </p>
        </div>
      )}

      <div className="-mx-4 overflow-x-auto px-4 pb-2 sm:mx-0 sm:px-0">
        <div className="flex min-w-max gap-3">
          {stages.map((stage) => {
            const items = grouped.get(stage.id) ?? [];
            return (
              <div
                key={stage.id}
                className="flex w-64 shrink-0 flex-col rounded-lg bg-gray-100 p-2"
              >
                <div className="mb-2 flex items-center justify-between gap-2 px-1">
                  <div className="flex min-w-0 items-center gap-2">
                    <span
                      className="h-2.5 w-2.5 shrink-0 rounded-full"
                      style={{ backgroundColor: stage.color }}
                      aria-hidden
                    />
                    <span className="truncate text-sm font-semibold">
                      {stage.name}
                    </span>
                  </div>
                  <Badge variant="secondary" className="shrink-0">
                    {items.length}
                  </Badge>
                </div>

                <div className="flex min-h-[80px] flex-col gap-2">
                  {items.length === 0 ? (
                    <p
                      className={cn(
                        "rounded-lg border border-dashed p-3 text-center text-xs text-muted-foreground"
                      )}
                    >
                      Пусто
                    </p>
                  ) : (
                    items.map((lead) => (
                      <LeadCard
                        key={lead.id}
                        lead={lead}
                        stages={stages}
                        onMoved={load}
                      />
                    ))
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}