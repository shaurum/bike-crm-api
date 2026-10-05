"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Phone,
  Mail,
  MessageSquare,
  Send,
  FileText,
  CalendarClock,
  Wallet,
  User,
  Bike as BikeIcon,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { leadsApi, customersApi, bikesApi } from "@/lib/api";
import { formatCurrency } from "@/lib/utils";

interface Stage {
  id: string;
  name: string;
  color: string;
}

interface Source {
  id: string;
  name: string;
}

interface Comment {
  id: string;
  text: string;
  created_at: string;
  author?: { full_name: string } | null;
}

interface LeadDetail {
  id: string;
  client_name: string | null;
  client_phone: string | null;
  client_email: string | null;
  initial_message: string | null;
  stage_id: string | null;
  source?: Source | null;
  customer_id: string | null;
  bike_id: string | null;
  amount: number | null;
  deal_due_at: string | null;
  rental_start_at: string | null;
  rental_end_at: string | null;
  comments: Comment[];
}

interface CustomerOption {
  id: string;
  full_name: string;
  phone: string | null;
}

interface BikeOption {
  id: string;
  model: string;
  frame_number: string | null;
  is_rented: boolean;
  status: string;
  linked_lead_id: string | null;
}

const NONE = "__none__";

function toLocalInput(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(
    d.getHours()
  )}:${pad(d.getMinutes())}`;
}

function fromLocalInput(value: string): string | null {
  if (!value) return null;
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? null : d.toISOString();
}

function Field({
  label,
  icon: Icon,
  children,
  hint,
}: {
  label: string;
  icon: typeof User;
  children: React.ReactNode;
  hint?: string;
}) {
  return (
    <div className="space-y-1.5">
      <label className="flex items-center gap-1.5 text-sm font-medium">
        <Icon className="h-3.5 w-3.5 text-muted-foreground" aria-hidden />
        {label}
      </label>
      {children}
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}

export function LeadDetailDialog({
  leadId,
  open,
  onOpenChange,
  stages,
  onSaved,
}: {
  leadId: string | null;
  open: boolean;
  onOpenChange: (v: boolean) => void;
  stages: Stage[];
  onSaved: () => void;
}) {
  const [lead, setLead] = useState<LeadDetail | null>(null);
  const [sources, setSources] = useState<Source[]>([]);
  const [customers, setCustomers] = useState<CustomerOption[]>([]);
  const [bikes, setBikes] = useState<BikeOption[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [comment, setComment] = useState("");
  const [error, setError] = useState("");

  const [customerId, setCustomerId] = useState<string>(NONE);
  const [bikeId, setBikeId] = useState<string>(NONE);
  const [amount, setAmount] = useState("");
  const [dealDue, setDealDue] = useState("");
  const [rentalStart, setRentalStart] = useState("");
  const [rentalEnd, setRentalEnd] = useState("");
  const [stageId, setStageId] = useState<string>("");

  const hydrate = useCallback((data: LeadDetail) => {
    setLead(data);
    setCustomerId(data.customer_id ?? NONE);
    setBikeId(data.bike_id ?? NONE);
    setAmount(data.amount != null ? String(data.amount) : "");
    setDealDue(toLocalInput(data.deal_due_at));
    setRentalStart(toLocalInput(data.rental_start_at));
    setRentalEnd(toLocalInput(data.rental_end_at));
    setStageId(data.stage_id ?? "");
  }, []);

  const load = useCallback(async () => {
    if (!leadId) return;
    setLoading(true);
    setError("");
    try {
      const [leadRes, srcRes, custRes, bikesRes] = await Promise.all([
        leadsApi.get(leadId),
        leadsApi.sources(),
        customersApi.list({ size: 100 }),
        bikesApi.list({ size: 100 }),
      ]);
      hydrate(leadRes.data as LeadDetail);
      setSources(srcRes.data as Source[]);
      setCustomers(custRes.data?.items ?? []);
      setBikes(bikesRes.data?.items ?? []);
    } catch (err: any) {
      setError(err.response?.data?.detail || "Не удалось загрузить лид");
    } finally {
      setLoading(false);
    }
  }, [leadId, hydrate]);

  useEffect(() => {
    if (open) load();
    else {
      setLead(null);
      setComment("");
      setError("");
    }
  }, [open, load]);

  const saveStage = async (nextStageId: string) => {
    if (!lead || nextStageId === lead.stage_id) return;
    const previous = lead.stage_id;
    setStageId(nextStageId);
    setLead({ ...lead, stage_id: nextStageId });
    try {
      await leadsApi.changeStage(lead.id, nextStageId);
      onSaved();
    } catch {
      setStageId(previous ?? "");
      setLead({ ...lead, stage_id: previous });
    }
  };

  const saveDeal = async () => {
    if (!lead) return;
    setSaving(true);
    setError("");
    try {
      const res = await leadsApi.updateDeal(lead.id, {
        customer_id: customerId === NONE ? null : customerId,
        bike_id: bikeId === NONE ? null : bikeId,
        amount: amount ? Number(amount) : null,
        deal_due_at: fromLocalInput(dealDue),
        rental_start_at: fromLocalInput(rentalStart),
        rental_end_at: fromLocalInput(rentalEnd),
      });
      hydrate(res.data as LeadDetail);
      onSaved();
    } catch (err: any) {
      setError(err.response?.data?.detail || "Не удалось сохранить");
    } finally {
      setSaving(false);
    }
  };

  const sendComment = async () => {
    if (!lead || !comment.trim()) return;
    setSaving(true);
    try {
      const res = await leadsApi.addComment(lead.id, comment.trim());
      setLead({ ...lead, comments: [...lead.comments, res.data] });
      setComment("");
    } catch (err: any) {
      setError(err.response?.data?.detail || "Не удалось добавить комментарий");
    } finally {
      setSaving(false);
    }
  };

  // Байк, занятый другой сделкой, выдавать нельзя
  const availableBikes = bikes.filter(
    (b) => !b.linked_lead_id || b.linked_lead_id === lead?.id
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[92vh] flex-col gap-0 overflow-hidden p-0 sm:max-w-2xl">
        <div className="shrink-0 border-b px-5 pb-4 pt-5">
          <DialogHeader>
            <DialogTitle className="flex flex-wrap items-center gap-2">
              {lead?.client_name || "Лид"}
              {lead?.source?.name && (
                <Badge variant="secondary">{lead.source.name}</Badge>
              )}
            </DialogTitle>
            <DialogDescription className="flex flex-wrap gap-x-4 gap-y-1">
              {lead?.client_phone && (
                <span className="flex items-center gap-1">
                  <Phone className="h-3 w-3" aria-hidden />
                  {lead.client_phone}
                </span>
              )}
              {lead?.client_email && (
                <span className="flex items-center gap-1">
                  <Mail className="h-3 w-3" aria-hidden />
                  {lead.client_email}
                </span>
              )}
            </DialogDescription>
          </DialogHeader>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">

        {loading && (
          <p className="py-6 text-center text-sm text-muted-foreground">
            Загружаем карточку…
          </p>
        )}

        {error && (
          <p className="rounded-md bg-red-50 p-3 text-sm text-red-600">{error}</p>
        )}

        {lead && !loading && (
          <div className="space-y-5">
            <Field label="Стадия" icon={CalendarClock}>
              <Select value={stageId} onValueChange={saveStage}>
                <SelectTrigger>
                  <SelectValue placeholder="Выберите стадию" />
                </SelectTrigger>
                <SelectContent>
                  {stages.map((s) => (
                    <SelectItem key={s.id} value={s.id}>
                      {s.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>

            {lead.initial_message && (
              <div className="rounded-md bg-gray-50 p-3 text-sm">
                <p className="mb-1 font-medium">Сообщение клиента</p>
                <p className="text-muted-foreground">{lead.initial_message}</p>
              </div>
            )}

            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Клиент" icon={User} hint="Привязать существующего клиента">
                <Select value={customerId} onValueChange={setCustomerId}>
                  <SelectTrigger>
                    <SelectValue placeholder="Не выбран" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={NONE}>Не выбран</SelectItem>
                    {customers.map((c) => (
                      <SelectItem key={c.id} value={c.id}>
                        {c.full_name}
                        {c.phone ? ` · ${c.phone}` : ""}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Field>

              <Field
                label="Байк"
                icon={BikeIcon}
                hint={
                  availableBikes.length === 0
                    ? "Все байки заняты другими сделками"
                    : "Занятые байки другими сделками недоступны"
                }
              >
                <Select value={bikeId} onValueChange={setBikeId}>
                  <SelectTrigger>
                    <SelectValue placeholder="Не выбран" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={NONE}>Не выбран</SelectItem>
                    {availableBikes.map((b) => (
                      <SelectItem key={b.id} value={b.id}>
                        {b.model}
                        {b.frame_number ? ` · ${b.frame_number}` : ""}
                        {b.is_rented || b.status === "rented" ? " (в аренде)" : ""}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Field>

              <Field label="Сумма, ₽" icon={Wallet}>
                <Input
                  type="number"
                  inputMode="decimal"
                  min={0}
                  step="0.01"
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                  placeholder="0"
                />
              </Field>

              <Field label="Срок появления сделки" icon={CalendarClock}>
                <Input
                  type="datetime-local"
                  value={dealDue}
                  onChange={(e) => setDealDue(e.target.value)}
                />
              </Field>

              <Field label="Начало аренды" icon={CalendarClock}>
                <Input
                  type="datetime-local"
                  value={rentalStart}
                  onChange={(e) => setRentalStart(e.target.value)}
                />
              </Field>

              <Field label="Окончание аренды" icon={CalendarClock}>
                <Input
                  type="datetime-local"
                  value={rentalEnd}
                  onChange={(e) => setRentalEnd(e.target.value)}
                />
              </Field>
            </div>

            <Button
              variant="outline"
              disabled
              className="w-full sm:w-auto"
              title="Функционал появится позже"
            >
              <FileText className="mr-2 h-4 w-4" aria-hidden />
              Сгенерировать документ
            </Button>

            <div className="space-y-3 border-t pt-4">
              <p className="flex items-center gap-1.5 text-sm font-semibold">
                <MessageSquare className="h-4 w-4" aria-hidden />
                Комментарии менеджеров
              </p>

              {lead.comments.length === 0 ? (
                <p className="text-sm text-muted-foreground">Комментариев пока нет</p>
              ) : (
                <ul className="space-y-2">
                  {lead.comments.map((c) => (
                    <li key={c.id} className="rounded-md bg-gray-50 p-3 text-sm">
                      <p className="mb-1 text-xs font-medium text-muted-foreground">
                        {c.author?.full_name ?? "Менеджер"} ·{" "}
                        {new Date(c.created_at).toLocaleString("ru-RU")}
                      </p>
                      <p className="whitespace-pre-wrap">{c.text}</p>
                    </li>
                  ))}
                </ul>
              )}

              <div className="flex gap-2">
                <Input
                  value={comment}
                  onChange={(e) => setComment(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      sendComment();
                    }
                  }}
                  placeholder="Добавить комментарий…"
                />
                <Button onClick={sendComment} disabled={saving || !comment.trim()}>
                  <Send className="h-4 w-4" aria-hidden />
                </Button>
              </div>
            </div>

            </div>
        )}
        </div>

        <div className="shrink-0 border-t bg-white px-5 py-3">
          <div className="flex items-center justify-end gap-2">
            {lead?.amount != null && (
              <p className="mr-auto text-sm text-muted-foreground">
                Сумма:{" "}
                <span className="font-semibold text-foreground">
                  {formatCurrency(lead.amount)}
                </span>
              </p>
            )}
            <Button onClick={saveDeal} disabled={saving || !lead}>
              {saving ? "Сохраняем…" : "Сохранить"}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}