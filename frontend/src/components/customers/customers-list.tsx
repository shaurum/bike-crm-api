"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Plus,
  RefreshCw,
  Trash2,
  EyeOff,
  Upload,
  User,
  Phone,
  Mail,
  MapPin,
  Cake,
  FileText,
  Ban,
  Pencil,
  Search,
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
  DialogDescription,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { customersApi, api, API_URL } from "@/lib/api";
import { ChannelIcon } from "@/components/channel-icon";
import { apiErrorMessage, cn } from "@/lib/utils";
import { toast } from "@/hooks/use-toast";

interface CustomerDoc {
  id: string;
  kind: string;
  file_url: string;
  original_name: string | null;
  size: number | null;
  created_at: string;
}

interface Customer {
  id: string;
  full_name: string;
  phone: string;
  email: string | null;
  document_type: string;
  country: string;
  birth_date: string | null;
  birth_place: string | null;
  passport_series: string | null;
  passport_number: string | null;
  passport_code: string | null;
  passport_issued_by: string | null;
  passport_issued_date: string | null;
  address: string | null;
  notes: string | null;
  is_blacklisted: boolean;
  documents: CustomerDoc[];
  created_at: string;
}

const DOC_TYPES = [
  { value: "passport_rf", label: "Паспорт РФ" },
  { value: "foreign_passport", label: "Загранпаспорт" },
  { value: "residence_permit", label: "РВП / ВНЖ" },
  { value: "id_card", label: "ID-карта" },
  { value: "driver_license", label: "Вод. удостоверение" },
  { value: "other", label: "Другой документ" },
];

// Примеры под российский паспорт, чтобы было понятно, чего ждёт форма
const RF_EXAMPLES: Record<string, string> = {
  series: "45 12",
  number: "123456",
  code: "001-002",
  issued_by: "ГУ МВД России по г. Москве",
  country: "Россия",
};

const DOC_LABELS: Record<string, string> = Object.fromEntries(
  DOC_TYPES.map((d) => [d.value, d.label])
);

const NO = "__none__";

function passportLabel(c: Customer): string {
  const series = c.passport_series ?? "";
  const number = c.passport_number ?? "";
  const code = c.passport_code ? `-${c.passport_code}` : "";
  const parts = `${series} ${number}${code}`.trim();
  return parts || "—";
}

function ageFrom(birth: string | null): number | null {
  if (!birth) return null;
  const d = new Date(birth);
  if (Number.isNaN(d.getTime())) return null;
  const now = new Date();
  let age = now.getFullYear() - d.getFullYear();
  const m = now.getMonth() - d.getMonth();
  if (m < 0 || (m === 0 && now.getDate() < d.getDate())) age--;
  return age;
}

function ageFromInput(birth: string): number | null {
  if (!birth) return null;
  const d = new Date(birth);
  if (Number.isNaN(d.getTime())) return null;
  const now = new Date();
  let age = now.getFullYear() - d.getFullYear();
  const m = now.getMonth() - d.getMonth();
  if (m < 0 || (m === 0 && now.getDate() < d.getDate())) age--;
  return age;
}

function toDateInput(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toISOString().slice(0, 10);
}

function toDateTimeInput(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(
    d.getHours()
  )}:${pad(d.getMinutes())}`;
}

function formatBytes(size: number | null): string {
  if (!size) return "";
  if (size < 1024) return `${size} Б`;
  if (size < 1024 * 1024) return `${Math.round(size / 1024)} КБ`;
  return `${(size / 1024 / 1024).toFixed(1)} МБ`;
}

/* ------------------------------------------------------------------ */
/* Карточка клиента                                                    */
/* ------------------------------------------------------------------ */

function CustomerCard({
  customer,
  onOpen,
}: {
  customer: Customer;
  onOpen: (id: string) => void;
}) {
  const age = ageFrom(customer.birth_date);
  const hasPassport = Boolean(customer.passport_number);

  return (
    <button
      type="button"
      onClick={() => onOpen(customer.id)}
      className="flex w-full cursor-pointer flex-col gap-3 rounded-lg border bg-white p-4 text-left shadow-sm transition-shadow hover:shadow-md"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate font-semibold leading-tight">
            {customer.full_name}
          </p>
          <p className="mt-0.5 flex items-center gap-1.5 truncate text-xs text-muted-foreground">
            <Phone className="h-3 w-3 shrink-0" aria-hidden />
            {customer.phone}
          </p>
        </div>
        {customer.is_blacklisted && (
          <Badge variant="destructive" className="shrink-0">
            <Ban className="mr-1 h-3 w-3" aria-hidden />
            Стоп-лист
          </Badge>
        )}
      </div>

      <div className="flex flex-wrap gap-1.5">
        {hasPassport ? (
          <Badge variant="secondary">
            {DOC_LABELS[customer.document_type] ?? customer.document_type}
          </Badge>
        ) : (
          <Badge variant="outline" className="text-amber-600">
            Паспорт не заполнен
          </Badge>
        )}
        {customer.country && customer.country !== "Россия" && (
          <Badge variant="outline">{customer.country}</Badge>
        )}
        {age != null && <Badge variant="outline">{age} лет</Badge>}
        {customer.documents.length > 0 && (
          <Badge variant="outline">
            <FileText className="mr-1 h-3 w-3" aria-hidden />
            {customer.documents.length}
          </Badge>
        )}
      </div>

      <div className="mt-auto space-y-1 border-t pt-2 text-xs">
        <p className="flex items-center justify-between gap-2">
          <span className="text-muted-foreground">Паспорт</span>
          <span className={cn("truncate", !hasPassport && "text-amber-600")}>
            {hasPassport ? passportLabel(customer) : "не заполнен"}
          </span>
        </p>
        <p className="flex items-center justify-between gap-2">
          <span className="text-muted-foreground">Дата рождения</span>
          <span className={cn("truncate", !customer.birth_date && "text-amber-600")}>
            {customer.birth_date ?? "не указана"}
          </span>
        </p>
      </div>
    </button>
  );
}

/* ------------------------------------------------------------------ */
/* Каналы связи клиента (contact_point): их может быть несколько       */
/* ------------------------------------------------------------------ */

interface ContactPoint {
  id: string;
  channel: string;
  value: string;
  label: string | null;
  is_primary: boolean;
  is_verified: boolean;
}

const CONTACT_CHANNELS = [
  { value: "phone", label: "Телефон" },
  { value: "email", label: "Почта" },
  { value: "telegram", label: "Telegram" },
  { value: "whatsapp", label: "WhatsApp" },
  { value: "vk", label: "ВКонтакте" },
  { value: "avito", label: "Авито" },
];

const CONTACT_CHANNEL_LABELS: Record<string, string> = Object.fromEntries(
  CONTACT_CHANNELS.map((c) => [c.value, c.label])
);

function contactPlaceholder(channel: string): string {
  switch (channel) {
    case "email":
      return "mail@example.com";
    case "telegram":
      return "@username";
    case "vk":
      return "screen name или ссылка";
    case "avito":
      return "ID клиента на Авито";
    default:
      return "+79001234567";
  }
}

function normContactValue(channel: string, v: string): string {
  const raw = v.trim().toLowerCase();
  if (channel === "phone") return raw.replace(/[^\d+]/g, "");
  if (channel === "telegram") return raw.replace(/^@/, "");
  return raw;
}

type DupDetail = {
  code: "duplicate";
  scope: "same" | "other";
  contact_id: string;
  customer_id: string;
  customer_name: string;
  is_primary: boolean;
  value: string;
  action?: "add" | "edit";
};

function ContactPointsSection({
  customerId,
  reloadKey,
}: {
  customerId: string;
  reloadKey: number;
}) {
  const [contacts, setContacts] = useState<ContactPoint[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [adding, setAdding] = useState(false);
  const [channel, setChannel] = useState("phone");
  const [value, setValue] = useState("");
  const [label, setLabel] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState<ContactPoint | null>(null);
  const [editValue, setEditValue] = useState("");
  const [editLabel, setEditLabel] = useState("");
  const [dup, setDup] = useState<DupDetail | null>(null);

  const handleDup = (err: any, action: "add" | "edit") => {
    const d = err.response?.data?.detail;
    if (d && d.code === "duplicate") {
      setDup({ ...d, action });
      return;
    }
    setError(
      typeof d === "string"
        ? d
        : action === "add"
          ? "Не удалось добавить контакт"
          : "Не удалось изменить контакт"
    );
  };

  const load = useCallback(async () => {
    try {
      const res = await api.get<ContactPoint[]>(
        `/conversations/contacts/${customerId}`
      );
      setContacts(res.data);
      setLoaded(true);
    } catch {
      setLoaded(true);
    }
  }, [customerId]);

  useEffect(() => {
    if (customerId) load();
  }, [customerId, reloadKey, load]);

  const add = async (force = false) => {
    if (!value.trim()) return;
    setBusy(true);
    setError("");
    try {
      await api.post(`/conversations/contacts/${customerId}`, {
        channel,
        value: value.trim(),
        label: label.trim() || null,
        force,
      });
      setValue("");
      setLabel("");
      setAdding(false);
      setDup(null);
      await load();
    } catch (err: any) {
      handleDup(err, "add");
    } finally {
      setBusy(false);
    }
  };

  const remove = async (id: string) => {
    setBusy(true);
    setError("");
    try {
      await api.delete(`/conversations/contacts/${id}`);
      await load();
    } catch (err: any) {
      setError(apiErrorMessage(err, "Не удалось удалить контакт"));
    } finally {
      setBusy(false);
    }
  };

  const startEdit = (contact: ContactPoint) => {
    setEditing(contact);
    setEditValue(contact.value);
    setEditLabel(contact.label || "");
    setAdding(false);
    setDup(null);
  };

  const saveEdit = async (force = false) => {
    if (!editing || !editValue.trim()) return;
    setBusy(true);
    setError("");
    try {
      await api.patch(`/conversations/contacts/${editing.id}`, {
        value: editValue.trim(),
        label: editLabel.trim() || null,
        force,
      });
      setEditing(null);
      setDup(null);
      await load();
    } catch (err: any) {
      handleDup(err, "edit");
    } finally {
      setBusy(false);
    }
  };

  // Объединение: удаляем дубль, повторяем операцию, сохраняем «основной»
  const mergeDuplicate = async () => {
    if (!dup) return;
    setBusy(true);
    setError("");
    try {
      const wasPrimary = dup.is_primary;
      await api.delete(`/conversations/contacts/${dup.contact_id}`);
      if (dup.action === "add") {
        const res = await api.post<ContactPoint>(
          `/conversations/contacts/${customerId}`,
          {
            channel,
            value: value.trim(),
            label: label.trim() || null,
          }
        );
        if (wasPrimary) {
          await api.patch(`/conversations/contacts/${res.data.id}`, {
            is_primary: true,
          });
        }
        setValue("");
        setLabel("");
        setAdding(false);
      } else if (editing) {
        const res = await api.patch<ContactPoint>(
          `/conversations/contacts/${editing.id}`,
          {
            value: editValue.trim(),
            label: editLabel.trim() || null,
          }
        );
        if (wasPrimary && !editing.is_primary) {
          await api.patch(`/conversations/contacts/${res.data.id}`, {
            is_primary: true,
          });
        }
        setEditing(null);
      }
      setDup(null);
      await load();
    } catch (err: any) {
      handleDup(err, dup.action || "add");
    } finally {
      setBusy(false);
    }
  };

  const forceAnyway = async () => {
    if (!dup) return;
    const action = dup.action;
    setDup(null);
    if (action === "edit") {
      await saveEdit(true);
    } else {
      await add(true);
    }
  };

  const makePrimary = async (contact: ContactPoint) => {
    if (contact.is_primary) return;
    setBusy(true);
    setError("");
    try {
      await api.patch(`/conversations/contacts/${contact.id}`, {
        is_primary: true,
      });
      await load();
    } catch (err: any) {
      setError(apiErrorMessage(err, "Не удалось изменить контакт"));
    } finally {
      setBusy(false);
    }
  };

  const liveDupTarget = (() => {
    if (editing) {
      const v = normContactValue(editing.channel, editValue);
      if (!v) return null;
      return (
        contacts.find(
          (c) =>
            c.id !== editing.id &&
            c.channel === editing.channel &&
            normContactValue(c.channel, c.value) === v
        ) || null
      );
    }
    const v = normContactValue(channel, value);
    if (!v) return null;
    return (
      contacts.find(
        (c) =>
          c.channel === channel && normContactValue(c.channel, c.value) === v
      ) || null
    );
  })();

  return (
    <div className="space-y-3 rounded-lg border p-3">
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold">Каналы связи</p>
        <button
          type="button"
          onClick={() => {
            setEditing(null);
            setDup(null);
            setAdding((v) => !v);
          }}
          className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
        >
          <Plus className="h-3 w-3" aria-hidden />
          Добавить
        </button>
      </div>

      {error && <p className="text-xs text-red-600">{error}</p>}

      {dup && (
        <div className="space-y-2 rounded-md border border-amber-300 bg-amber-50 p-2.5 text-xs text-amber-900">
          {dup.scope === "same" ? (
            <>
              <p>
                Такой контакт у клиента уже есть. Объединить: дубль удалим,
                оставим {dup.action === "add" ? "новый" : "изменённый"} контакт.
              </p>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={mergeDuplicate}
                  disabled={busy}
                  className="rounded-md bg-amber-600 px-2.5 py-1 text-white disabled:opacity-50"
                >
                  Объединить
                </button>
                <button
                  type="button"
                  onClick={() => setDup(null)}
                  className="rounded-md border border-amber-300 bg-white px-2.5 py-1"
                >
                  Отмена
                </button>
              </div>
            </>
          ) : (
            <>
              <p>
                Контакт «{dup.value}» уже есть у клиента «{dup.customer_name}
                ». Добавить всё равно?
              </p>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={forceAnyway}
                  disabled={busy}
                  className="rounded-md bg-amber-600 px-2.5 py-1 text-white disabled:opacity-50"
                >
                  Всё равно {dup.action === "add" ? "добавить" : "сохранить"}
                </button>
                <button
                  type="button"
                  onClick={() => setDup(null)}
                  className="rounded-md border border-amber-300 bg-white px-2.5 py-1"
                >
                  Отмена
                </button>
              </div>
            </>
          )}
        </div>
      )}

      {loaded && contacts.length === 0 && !adding && (
        <p className="text-xs text-muted-foreground">
          Контактов пока нет — добавьте телефон, почту или мессенджер
        </p>
      )}

      <ul className="space-y-1.5">
        {contacts.map((contact) => (
          <li
            key={contact.id}
            className="flex items-center justify-between gap-2 rounded-md border px-2 py-1.5"
          >
            {editing?.id === contact.id ? (
              <>
                <div className="min-w-0 flex-1 space-y-1.5">
                  <input
                    value={editValue}
                    onChange={(e) => setEditValue(e.target.value)}
                    placeholder={contactPlaceholder(contact.channel)}
                    className="w-full rounded-md border bg-background px-2 py-1 text-sm outline-none focus:ring-2 focus:ring-ring"
                  />
                  <input
                    value={editLabel}
                    onChange={(e) => setEditLabel(e.target.value)}
                    placeholder="Подпись (необязательно)"
                    className="w-full rounded-md border bg-background px-2 py-1 text-sm outline-none focus:ring-2 focus:ring-ring"
                  />
                  {liveDupTarget && (
                    <p className="text-[11px] text-amber-700">
                      Такой контакт уже есть — при сохранении предложим
                      объединить
                    </p>
                  )}
                </div>
                <div className="flex shrink-0 items-center gap-1.5">
                  <button
                    type="button"
                    onClick={() => saveEdit()}
                    disabled={!editValue.trim() || busy}
                    className="rounded-md bg-primary px-2.5 py-1 text-xs text-primary-foreground disabled:opacity-50"
                  >
                    {busy ? "…" : "Сохранить"}
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setEditing(null);
                      setDup(null);
                    }}
                    className="rounded-md border px-2.5 py-1 text-xs"
                  >
                    Отмена
                  </button>
                </div>
              </>
            ) : (
              <>
                <div className="flex min-w-0 items-center gap-2">
                  <ChannelIcon channel={contact.channel} className="h-4 w-4 shrink-0" />
                  <div className="min-w-0">
                    <p className="truncate text-sm">{contact.value}</p>
                    <p className="truncate text-[11px] text-muted-foreground">
                      {CONTACT_CHANNEL_LABELS[contact.channel] || contact.channel}
                      {contact.label ? ` · ${contact.label}` : ""}
                    </p>
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-1">
                  {contact.is_primary ? (
                    <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
                      основной
                    </span>
                  ) : (
                    <button
                      type="button"
                      onClick={() => makePrimary(contact)}
                      disabled={busy}
                      className="hidden rounded px-1.5 py-0.5 text-[10px] text-muted-foreground hover:bg-muted sm:inline"
                      title="Сделать основным контактом канала"
                    >
                      основной
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => startEdit(contact)}
                    disabled={busy}
                    aria-label="Редактировать контакт"
                    className="flex h-7 w-7 items-center justify-center rounded text-gray-300 hover:bg-muted hover:text-gray-700"
                  >
                    <Pencil className="h-3.5 w-3.5" aria-hidden />
                  </button>
                  <button
                    type="button"
                    onClick={() => remove(contact.id)}
                    disabled={busy}
                    aria-label="Удалить контакт"
                    className="flex h-7 w-7 items-center justify-center rounded text-gray-300 hover:bg-red-50 hover:text-red-600"
                  >
                    <Trash2 className="h-3.5 w-3.5" aria-hidden />
                  </button>
                </div>
              </>
            )}
          </li>
        ))}
      </ul>

      {adding && (
        <div className="space-y-2 rounded-md border p-2">
          <select
            value={channel}
            onChange={(e) => setChannel(e.target.value)}
            className="w-full rounded-md border bg-background px-2 py-1.5 text-sm outline-none focus:ring-2 focus:ring-ring"
          >
            {CONTACT_CHANNELS.map((c) => (
              <option key={c.value} value={c.value}>
                {c.label}
              </option>
            ))}
          </select>
          <input
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder={contactPlaceholder(channel)}
            className="w-full rounded-md border bg-background px-2 py-1.5 text-sm outline-none focus:ring-2 focus:ring-ring"
          />
          <input
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="Подпись (необязательно)"
            className="w-full rounded-md border bg-background px-2 py-1.5 text-sm outline-none focus:ring-2 focus:ring-ring"
          />
          {liveDupTarget && (
            <p className="text-[11px] text-amber-700">
              Такой контакт уже есть — при сохранении предложим объединить
            </p>
          )}
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => add()}
              disabled={!value.trim() || busy}
              className="rounded-md bg-primary px-3 py-1.5 text-sm text-primary-foreground disabled:opacity-50"
            >
              {busy ? "…" : "Сохранить"}
            </button>
            <button
              type="button"
              onClick={() => {
                setAdding(false);
                setDup(null);
              }}
              className="rounded-md border px-3 py-1.5 text-sm"
            >
              Отмена
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Диалог клиента                                                      */
/* ------------------------------------------------------------------ */

export function CustomerDialog({
  customerId,
  open,
  onOpenChange,
  onSaved,
}: {
  customerId: string | null;
  open: boolean;
  onOpenChange: (v: boolean) => void;
  onSaved: () => void;
}) {
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState("");

  const [fullName, setFullName] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [docType, setDocType] = useState("passport_rf");
  const [country, setCountry] = useState("Россия");
  const [birthDate, setBirthDate] = useState("");
  const [birthPlace, setBirthPlace] = useState("");
  const [series, setSeries] = useState("");
  const [number, setNumber] = useState("");
  const [code, setCode] = useState("");
  const [issuedBy, setIssuedBy] = useState("");
  const [issuedDate, setIssuedDate] = useState("");
  const [address, setAddress] = useState("");
  const [notes, setNotes] = useState("");
  const [blacklisted, setBlacklisted] = useState(false);

  const fileRef = useRef<HTMLInputElement | null>(null);
  const [uploadKind, setUploadKind] = useState("passport_rf");
  // Каналы связи перечитываем после сохранения — телефон/email синхронизируются на сервере
  const [contactsVersion, setContactsVersion] = useState(0);

  const hydrate = useCallback((data: Customer) => {
    setCustomer(data);
    setFullName(data.full_name ?? "");
    setPhone(data.phone ?? "");
    setEmail(data.email ?? "");
    setDocType(data.document_type ?? "passport_rf");
    setCountry(data.country ?? "Россия");
    setBirthDate(toDateInput(data.birth_date));
    setBirthPlace(data.birth_place ?? "");
    setSeries(data.passport_series ?? "");
    setNumber(data.passport_number ?? "");
    setCode(data.passport_code ?? "");
    setIssuedBy(data.passport_issued_by ?? "");
    setIssuedDate(toDateTimeInput(data.passport_issued_date));
    setAddress(data.address ?? "");
    setNotes(data.notes ?? "");
    setBlacklisted(data.is_blacklisted);
    setUploadKind(data.document_type ?? "passport_rf");
  }, []);

  const load = useCallback(async () => {
    if (!customerId) return;
    setLoading(true);
    setError("");
    try {
      const res = await customersApi.get(customerId);
      hydrate(res.data as Customer);
    } catch (err: any) {
      setError(apiErrorMessage(err, "Не удалось загрузить клиента"));
    } finally {
      setLoading(false);
    }
  }, [customerId, hydrate]);

  useEffect(() => {
    if (open) load();
    else {
      setCustomer(null);
      setError("");
    }
  }, [open, load]);

  const save = async () => {
    if (!customer) return;
    setSaving(true);
    setError("");
    try {
      const res = await customersApi.update(customer.id, {
        full_name: fullName,
        phone,
        email: email || null,
        document_type: docType,
        country,
        birth_date: birthDate || null,
        birth_place: birthPlace || null,
        passport_series: series || null,
        passport_number: number || null,
        passport_code: code || null,
        passport_issued_by: issuedBy || null,
        passport_issued_date: issuedDate ? new Date(issuedDate).toISOString() : null,
        address: address || null,
        notes: notes || null,
        is_blacklisted: blacklisted,
      });
      hydrate(res.data as Customer);
      setContactsVersion((v) => v + 1);
      onSaved();
      onOpenChange(false);
    } catch (err: any) {
      setError(apiErrorMessage(err, "Не удалось сохранить"));
    } finally {
      setSaving(false);
    }
  };

  const uploadDoc = async (file: File) => {
    if (!customer) return;
    setSaving(true);
    setError("");
    try {
      await customersApi.uploadDocument(customer.id, file, uploadKind);
      await load();
      onSaved();
    } catch (err: any) {
      setError(apiErrorMessage(err, "Не удалось загрузить документ"));
    } finally {
      setSaving(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const removeDoc = async (docId: string) => {
    if (!customer) return;
    setSaving(true);
    try {
      await customersApi.removeDocument(customer.id, docId);
      await load();
      onSaved();
    } catch (err: any) {
      setError(apiErrorMessage(err, "Не удалось удалить документ"));
    } finally {
      setSaving(false);
    }
  };

  const removeCustomer = async () => {
    if (!customer) return;
    setDeleting(true);
    setDeleteError("");
    try {
      await customersApi.remove(customer.id);
      toast({
        title: "Клиент скрыт",
        description: customer.full_name,
      });
      onSaved();
      setConfirmDelete(false);
      onOpenChange(false);
    } catch (err: any) {
      setDeleteError(apiErrorMessage(err, "Не удалось удалить клиента"));
    } finally {
      setDeleting(false);
    }
  };

  const age = ageFromInput(birthDate);
  const needsDocs = (customer?.documents.length ?? 0) === 0;

  return (
    <>
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[92vh] flex-col gap-0 overflow-hidden p-0 sm:max-w-2xl">
        <div className="flex shrink-0 items-start justify-between gap-3 border-b px-5 pb-4 pt-5 pr-11">
          <DialogHeader>
            <DialogTitle>{customer?.full_name || "Клиент"}</DialogTitle>
            <DialogDescription>
              {customer?.phone}
              {age != null ? ` · ${age} лет` : ""}
            </DialogDescription>
          </DialogHeader>
          {customer && customer.is_blacklisted && (
            <Badge variant="destructive" className="shrink-0">
              Стоп-лист
            </Badge>
          )}
        </div>

        <div className="min-h-0 flex-1 space-y-5 overflow-y-auto px-5 py-4">
          {loading && (
            <p className="py-6 text-center text-sm text-muted-foreground">Загрузка…</p>
          )}
          {error && (
            <p className="rounded-md bg-red-50 p-3 text-sm text-red-600">{error}</p>
          )}

          {customer && !loading && (
            <>
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-1.5 sm:col-span-2">
                  <label className="flex items-center gap-1.5 text-sm font-medium" htmlFor="c-name">
                    <User className="h-3.5 w-3.5 text-muted-foreground" aria-hidden />
                    ФИО
                  </label>
                  <Input
                    id="c-name"
                    name="name"
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                  />
                </div>

                <div className="space-y-1.5">
                  <label className="flex items-center gap-1.5 text-sm font-medium" htmlFor="c-phone">
                    <Phone className="h-3.5 w-3.5 text-muted-foreground" aria-hidden />
                    Телефон
                  </label>
                  <Input
                    id="c-phone"
                    name="tel"
                    type="tel"
                    value={phone}
                    onChange={(e) => setPhone(e.target.value)}
                  />
                </div>

                <div className="space-y-1.5">
                  <label className="flex items-center gap-1.5 text-sm font-medium" htmlFor="c-email">
                    <Mail className="h-3.5 w-3.5 text-muted-foreground" aria-hidden />
                    Email
                  </label>
                  <Input
                    id="c-email"
                    name="email"
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                  />
                </div>
              </div>

              <ContactPointsSection
                customerId={customer.id}
                reloadKey={contactsVersion}
              />

              <div className="space-y-3 rounded-lg border p-3">
                <p className="text-sm font-semibold">Документ, удостоверяющий личность</p>
                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="space-y-1.5">
                    <label className="text-xs font-medium" htmlFor="c-doctype">
                      Тип документа
                    </label>
                    <Select value={docType} onValueChange={setDocType}>
                      <SelectTrigger id="c-doctype">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {DOC_TYPES.map((d) => (
                          <SelectItem key={d.value} value={d.value}>
                            {d.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="space-y-1.5">
                    <label className="text-xs font-medium" htmlFor="c-country">
                      Страна
                    </label>
                    <Input
                      id="c-country"
                      value={country}
                      onChange={(e) => setCountry(e.target.value)}
                    />
                  </div>

                  <div className="space-y-1.5">
                    <label className="text-xs font-medium" htmlFor="c-series">
                      Серия
                    </label>
                    <Input
                      id="c-series"
                      value={series}
                      onChange={(e) => setSeries(e.target.value)}
                      placeholder={RF_EXAMPLES.series}
                    />
                  </div>

                  <div className="space-y-1.5">
                    <label className="text-xs font-medium" htmlFor="c-number">
                      Номер
                    </label>
                    <Input
                      id="c-number"
                      value={number}
                      onChange={(e) => setNumber(e.target.value)}
                      placeholder={RF_EXAMPLES.number}
                    />
                  </div>

                  <div className="space-y-1.5">
                    <label className="text-xs font-medium" htmlFor="c-code">
                      Код подразделения
                    </label>
                    <Input
                      id="c-code"
                      value={code}
                      onChange={(e) => setCode(e.target.value)}
                      placeholder={RF_EXAMPLES.code}
                    />
                  </div>

                  <div className="space-y-1.5">
                    <label className="flex items-center gap-1.5 text-xs font-medium" htmlFor="c-birth">
                      <Cake className="h-3.5 w-3.5 text-muted-foreground" aria-hidden />
                      Дата рождения
                    </label>
                    <Input
                      id="c-birth"
                      type="date"
                      value={birthDate}
                      onChange={(e) => setBirthDate(e.target.value)}
                    />
                  </div>

                  <div className="space-y-1.5 sm:col-span-2">
                    <label className="text-xs font-medium" htmlFor="c-birthplace">
                      Место рождения
                    </label>
                    <Input
                      id="c-birthplace"
                      value={birthPlace}
                      onChange={(e) => setBirthPlace(e.target.value)}
                    />
                  </div>

                  <div className="space-y-1.5">
                    <label className="text-xs font-medium" htmlFor="c-issuedby">
                      Кем выдан
                    </label>
                    <Input
                      id="c-issuedby"
                      value={issuedBy}
                      onChange={(e) => setIssuedBy(e.target.value)}
                      placeholder={RF_EXAMPLES.issued_by}
                    />
                  </div>

                  <div className="space-y-1.5">
                    <label className="text-xs font-medium" htmlFor="c-issueddate">
                      Когда выдан
                    </label>
                    <Input
                      id="c-issueddate"
                      type="date"
                      value={issuedDate ? issuedDate.slice(0, 10) : ""}
                      onChange={(e) => setIssuedDate(e.target.value)}
                    />
                  </div>

                  <div className="space-y-1.5 sm:col-span-2">
                    <label className="flex items-center gap-1.5 text-xs font-medium" htmlFor="c-address">
                      <MapPin className="h-3.5 w-3.5 text-muted-foreground" aria-hidden />
                      Адрес регистрации
                    </label>
                    <Input
                      id="c-address"
                      value={address}
                      onChange={(e) => setAddress(e.target.value)}
                    />
                  </div>
                </div>
              </div>

              <div className="space-y-2">
                <div className="flex flex-wrap items-end justify-between gap-3">
                  <p className="text-sm font-semibold">
                    Сканы документов
                    {needsDocs && (
                      <span className="ml-2 text-xs font-normal text-amber-600">
                        обязательны для договора
                      </span>
                    )}
                  </p>
                  <div className="flex items-center gap-2">
                    <Select value={uploadKind} onValueChange={setUploadKind}>
                      <SelectTrigger className="h-9 w-48">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {DOC_TYPES.map((d) => (
                          <SelectItem key={d.value} value={d.value}>
                            {d.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <input
                      ref={fileRef}
                      type="file"
                      accept="image/jpeg,image/png,image/webp,application/pdf"
                      className="hidden"
                      onChange={(e) => {
                        const f = e.target.files?.[0];
                        if (f) uploadDoc(f);
                      }}
                    />
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={saving}
                      onClick={() => fileRef.current?.click()}
                    >
                      <Upload className="mr-2 h-4 w-4" aria-hidden />
                      Загрузить
                    </Button>
                  </div>
                </div>

                {customer.documents.length === 0 ? (
                  <p className="rounded-md border border-dashed p-4 text-center text-sm text-muted-foreground">
                    Сканов пока нет
                  </p>
                ) : (
                  <ul className="space-y-2">
                    {customer.documents.map((doc) => (
                      <li
                        key={doc.id}
                        className="flex items-center gap-3 rounded-md border bg-white p-2.5"
                      >
                        <FileText className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
                        <div className="min-w-0 flex-1">
                          <a
                            href={`${API_URL}${doc.file_url}`}
                            target="_blank"
                            rel="noreferrer"
                            className="block truncate text-sm font-medium hover:underline"
                          >
                            {doc.original_name || doc.file_url}
                          </a>
                          <p className="text-xs text-muted-foreground">
                            {DOC_LABELS[doc.kind] ?? doc.kind} ·{" "}
                            {new Date(doc.created_at).toLocaleDateString("ru-RU")}
                            {formatBytes(doc.size) ? ` · ${formatBytes(doc.size)}` : ""}
                          </p>
                        </div>
                        <button
                          type="button"
                          onClick={() => removeDoc(doc.id)}
                          disabled={saving}
                          aria-label="Удалить документ"
                          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md text-gray-300 hover:bg-red-50 hover:text-red-600"
                        >
                          <Trash2 className="h-4 w-4" aria-hidden />
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
                <p className="text-xs text-muted-foreground">
                  JPG, PNG, WEBP или PDF до 8 МБ
                </p>
              </div>

              <div className="space-y-1.5">
                <label className="text-sm font-medium" htmlFor="c-notes">
                  Примечания
                </label>
                <textarea
                  id="c-notes"
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  rows={2}
                  className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                />
              </div>

              <label className="flex cursor-pointer items-center gap-2 rounded-md border p-3">
                <input
                  type="checkbox"
                  checked={blacklisted}
                  onChange={(e) => setBlacklisted(e.target.checked)}
                  className="h-4 w-4 accent-current"
                />
                <span className="text-sm">В стоп-листе — не выдавать байк</span>
              </label>
            </>
          )}
        </div>

        <div className="shrink-0 border-t bg-white px-5 py-3">
          <div className="flex items-center justify-between gap-2">
            <Button
              variant="outline"
              className="text-destructive hover:bg-destructive/10 hover:text-destructive"
              onClick={() => {
                setDeleteError("");
                setConfirmDelete(true);
              }}
              disabled={saving || !customer}
            >
              <EyeOff className="mr-2 h-4 w-4" aria-hidden />
              Скрыть
            </Button>
            <Button onClick={save} disabled={saving || !customer}>
              {saving ? "Сохраняем…" : "Сохранить"}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>

    <Dialog
      open={confirmDelete}
      onOpenChange={(v) => {
        if (!deleting) setConfirmDelete(v);
      }}
    >
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Скрыть клиента?</DialogTitle>
          <DialogDescription>
            Карточка «{customer?.full_name}» уйдёт из списка и поиска, но
            переписка, документы, история аренд и статистика сохранятся.
          </DialogDescription>
        </DialogHeader>

        {deleteError && (
          <p className="rounded-md bg-red-50 p-3 text-sm text-red-600">
            {deleteError}
          </p>
        )}

        <DialogFooter className="justify-end gap-2">
          <Button
            variant="outline"
            onClick={() => setConfirmDelete(false)}
            disabled={deleting}
          >
            Отмена
          </Button>
          <Button variant="destructive" onClick={removeCustomer} disabled={deleting}>
            {deleting ? "Скрываем…" : "Скрыть"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
    </>
  );
}

/* ------------------------------------------------------------------ */
/* Добавление клиента                                                  */
/* ------------------------------------------------------------------ */

function AddCustomerDialog({ onCreated }: { onCreated: () => void }) {
  const [open, setOpen] = useState(false);
  const [fullName, setFullName] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [docType, setDocType] = useState("passport_rf");
  const [country, setCountry] = useState("Россия");
  const [birthDate, setBirthDate] = useState("");
  const [series, setSeries] = useState("");
  const [number, setNumber] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError("");
    try {
      await customersApi.create({
        full_name: fullName.trim(),
        phone: phone.trim(),
        email: email.trim() || null,
        document_type: docType,
        country: country.trim() || "Россия",
        birth_date: birthDate || null,
        passport_series: series.trim() || null,
        passport_number: number.trim() || null,
      });
      setOpen(false);
      setFullName("");
      setPhone("");
      setEmail("");
      setSeries("");
      setNumber("");
      setBirthDate("");
      onCreated();
    } catch (err: any) {
      setError(apiErrorMessage(err, "Не удалось создать клиента"));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        setOpen(v);
        if (v) setError("");
      }}
    >
      <DialogTrigger asChild>
        <Button>
          <Plus className="mr-2 h-4 w-4" aria-hidden />
          Добавить клиента
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Новый клиент</DialogTitle>
          <DialogDescription>
            Остальные паспортные данные и сканы заполните в карточке.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={submit} className="space-y-3">
          <div className="space-y-1.5">
            <label className="text-sm font-medium" htmlFor="nc-name">
              ФИО
            </label>
            <Input
              id="nc-name"
              name="name"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              required
            />
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <label className="text-sm font-medium" htmlFor="nc-phone">
                Телефон
              </label>
              <Input
                id="nc-phone"
                name="tel"
                type="tel"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                required
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-sm font-medium" htmlFor="nc-email">
                Email
              </label>
              <Input
                id="nc-email"
                name="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <label className="text-xs font-medium" htmlFor="nc-doctype">
                Тип документа
              </label>
              <Select value={docType} onValueChange={setDocType}>
                <SelectTrigger id="nc-doctype">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {DOC_TYPES.map((d) => (
                    <SelectItem key={d.value} value={d.value}>
                      {d.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <label className="text-xs font-medium" htmlFor="nc-country">
                Страна
              </label>
              <Input
                id="nc-country"
                value={country}
                onChange={(e) => setCountry(e.target.value)}
              />
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-3">
            <div className="space-y-1.5">
              <label className="text-xs font-medium" htmlFor="nc-birth">
                Дата рождения
              </label>
              <Input
                id="nc-birth"
                type="date"
                value={birthDate}
                onChange={(e) => setBirthDate(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-xs font-medium" htmlFor="nc-series">
                Серия
              </label>
              <Input
                id="nc-series"
                value={series}
                onChange={(e) => setSeries(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-xs font-medium" htmlFor="nc-number">
                Номер
              </label>
              <Input
                id="nc-number"
                value={number}
                onChange={(e) => setNumber(e.target.value)}
              />
            </div>
          </div>

          {error && (
            <p className="rounded-md bg-red-50 p-2 text-sm text-red-600">{error}</p>
          )}

          <DialogFooter className="justify-end">
            <Button type="submit" disabled={saving}>
              {saving ? "Создаём…" : "Создать"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/* ------------------------------------------------------------------ */
/* Страница клиентов                                                  */
/* ------------------------------------------------------------------ */

export function CustomersList() {
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError("");
    try {
      const res = await customersApi.list({ size: 100, search: search || undefined });
      setCustomers((res.data?.items ?? []) as Customer[]);
      setTotal(res.data?.total ?? 0);
    } catch (err: any) {
      setError(apiErrorMessage(err, "Не удалось загрузить клиентов"));
    } finally {
      setLoading(false);
    }
  }, [search]);

  useEffect(() => {
    const t = setTimeout(load, search ? 300 : 0);
    return () => clearTimeout(t);
  }, [load, search]);

  const incomplete = useMemo(
    () =>
      customers.filter((c) => !c.passport_number || !c.birth_date).length,
    [customers]
  );

  if (loading) {
    return (
      <p className="py-10 text-center text-sm text-muted-foreground">Загружаем клиентов…</p>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Badge variant="secondary">Всего: {total}</Badge>
          {incomplete > 0 && (
            <Badge variant="outline" className="text-amber-600">
              Без паспорта или даты рождения: {incomplete}
            </Badge>
          )}
        </div>
        <div className="flex items-center gap-2">
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="ФИО, телефон или паспорт"
              className="h-9 w-64 pl-8"
            />
          </div>
          <Button variant="outline" size="sm" onClick={load}>
            <RefreshCw className="mr-2 h-4 w-4" aria-hidden />
            Обновить
          </Button>
          <AddCustomerDialog onCreated={load} />
        </div>
      </div>

      {error && (
        <p className="rounded-md bg-red-50 p-3 text-sm text-red-600">{error}</p>
      )}

      {customers.length === 0 ? (
        <p className="rounded-lg border border-dashed bg-white p-10 text-center text-sm text-muted-foreground">
          {search ? "Ничего не найдено" : "Клиентов пока нет"}
        </p>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {customers.map((customer) => (
            <CustomerCard
              key={customer.id}
              customer={customer}
              onOpen={setSelectedId}
            />
          ))}
        </div>
      )}

      <CustomerDialog
        customerId={selectedId}
        open={selectedId !== null}
        onOpenChange={(v) => {
          if (!v) setSelectedId(null);
        }}
        onSaved={load}
      />
    </div>
  );
}