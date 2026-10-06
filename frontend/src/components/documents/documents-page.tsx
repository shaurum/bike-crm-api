"use client";

import { useCallback, useEffect, useState } from "react";
import {
  FileText,
  Upload,
  Trash2,
  Download,
  RefreshCw,
  Building2,
  ExternalLink,
  X,
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
import { documentsApi, customersApi, API_URL } from "@/lib/api";

interface DocItem {
  id: string;
  customer_id: string | null;
  lead_id: string | null;
  kind: string;
  status: string;
  number: string | null;
  issued_at: string | null;
  file_url: string | null;
  original_name: string | null;
  size: number | null;
  signed_file_url: string | null;
  signed_original_name: string | null;
  signed_at: string | null;
  signed_size: number | null;
  payload: { incomplete?: string[] };
  created_at: string;
  customer?: { id: string; full_name: string } | null;
  bike_name?: string | null;
}

interface CustomerOption {
  id: string;
  full_name: string;
}

const KIND_LABELS: Record<string, string> = {
  contract_rental: "Договор аренды",
  act_handover: "Акт приёма-передачи",
  act_return: "Акт возврата",
  memo: "Памятка",
  scan: "Скан",
  other: "Прочее",
};

const STATUS_LABELS: Record<string, string> = {
  draft: "Черновик",
  issued: "Выдан",
  signed: "Подписан",
  cancelled: "Отменён",
};

const NO = "__none__";

function formatBytes(size: number | null): string {
  if (!size) return "";
  if (size < 1024) return `${size} Б`;
  if (size < 1024 * 1024) return `${Math.round(size / 1024)} КБ`;
  return `${(size / 1024 / 1024).toFixed(1)} МБ`;
}

function fmtDate(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleDateString("ru-RU");
}

/* ------------------------------------------------------------------ */
/* Реквизиты арендодателя                                              */
/* ------------------------------------------------------------------ */

function CompanyDialog() {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await documentsApi.company();
      setData(res.data as Record<string, string>);
    } catch (err: any) {
      setError(err.response?.data?.detail || "Не удалось загрузить реквизиты");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open) load();
  }, [open, load]);

  const set = (key: string) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setData((prev) => ({ ...prev, [key]: e.target.value }));

  const save = async () => {
    setSaving(true);
    try {
      const res = await documentsApi.updateCompany(data);
      setData(res.data as Record<string, string>);
      setOpen(false);
    } catch (err: any) {
      setError(err.response?.data?.detail || "Не удалось сохранить");
    } finally {
      setSaving(false);
    }
  };

  const fields: { key: string; label: string; placeholder?: string }[] = [
    { key: "name", label: "Название или ФИО ИП", placeholder: "ИП Леончук Анна Владимировна" },
    { key: "ogrnip", label: "ОГРНИП", placeholder: "3127746..." },
    { key: "inn", label: "ИНН", placeholder: "7728..." },
    { key: "phone", label: "Телефон", placeholder: "+7 999 123-45-67" },
    { key: "email", label: "Email" },
    { key: "address", label: "Адрес", placeholder: "Москва, ул. ..." },
    { key: "return_address", label: "Адрес возврата" },
    { key: "age_restriction", label: "Возрастное ограничение", placeholder: "18 лет" },
    { key: "deposit_return", label: "Порядок возврата залога" },
    { key: "photo_consent", label: "Согласие на фото/видео" },
  ];

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">
          <Building2 className="mr-2 h-4 w-4" aria-hidden />
          Реквизиты арендодателя
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Реквизиты арендодателя</DialogTitle>
          <DialogDescription>
            Подставляются в договор в разделах 1 и 15.
          </DialogDescription>
        </DialogHeader>

        {loading ? (
          <p className="py-6 text-center text-sm text-muted-foreground">Загрузка…</p>
        ) : (
          <div className="max-h-[60vh] space-y-3 overflow-y-auto">
            {error && (
              <p className="rounded-md bg-red-50 p-2 text-sm text-red-600">{error}</p>
            )}
            {fields.map((f) => (
              <div key={f.key} className="space-y-1.5">
                <label className="text-xs font-medium" htmlFor={`co-${f.key}`}>
                  {f.label}
                </label>
                <Input
                  id={`co-${f.key}`}
                  value={data[f.key] ?? ""}
                  onChange={set(f.key)}
                  placeholder={f.placeholder}
                />
              </div>
            ))}
          </div>
        )}

        <DialogFooter className="justify-end">
          <Button onClick={save} disabled={saving || loading}>
            {saving ? "Сохраняем…" : "Сохранить"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/* ------------------------------------------------------------------ */
/* Загрузка подписанного скана                                         */
/* ------------------------------------------------------------------ */

function UploadScanDialog({
  customers,
  onUploaded,
}: {
  customers: CustomerOption[];
  onUploaded: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [customerId, setCustomerId] = useState<string>(NO);
  const [number, setNumber] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const submit = async () => {
    if (!file) {
      setError("Выберите файл");
      return;
    }
    setSaving(true);
    setError("");
    try {
      await documentsApi.uploadScan(file, {
        customer_id: customerId === NO ? null : customerId,
        number: number || null,
      });
      setOpen(false);
      setFile(null);
      setNumber("");
      onUploaded();
    } catch (err: any) {
      setError(err.response?.data?.detail || "Не удалось загрузить");
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
          <Upload className="mr-2 h-4 w-4" aria-hidden />
          Загрузить скан
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Подписанный документ</DialogTitle>
          <DialogDescription>
            Загрузите подписанный договор или акт, чтобы хранить его в архиве.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <div className="space-y-1.5">
            <label className="text-sm font-medium" htmlFor="sc-customer">
              Клиент
            </label>
            <Select value={customerId} onValueChange={setCustomerId}>
              <SelectTrigger id="sc-customer">
                <SelectValue placeholder="Не указан" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NO}>Не указан</SelectItem>
                {customers.map((c) => (
                  <SelectItem key={c.id} value={c.id}>
                    {c.full_name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <label className="text-sm font-medium" htmlFor="sc-number">
              Номер документа
            </label>
            <Input
              id="sc-number"
              value={number}
              onChange={(e) => setNumber(e.target.value)}
              placeholder="Д-0001"
            />
          </div>

          <div className="space-y-1.5">
            <label className="text-sm font-medium" htmlFor="sc-file">
              Файл
            </label>
            <input
              id="sc-file"
              type="file"
              accept="image/jpeg,image/png,image/webp,application/pdf"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              className="w-full rounded-md border border-input bg-background p-2 text-sm file:mr-3 file:rounded file:border-0 file:bg-gray-100 file:px-2 file:py-1"
            />
            <p className="text-xs text-muted-foreground">JPG, PNG, WEBP или PDF до 8 МБ</p>
          </div>

          {error && (
            <p className="rounded-md bg-red-50 p-2 text-sm text-red-600">{error}</p>
          )}
        </div>

        <DialogFooter className="justify-end">
          <Button onClick={submit} disabled={saving}>
            {saving ? "Загружаем…" : "Загрузить"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/* ------------------------------------------------------------------ */
/* Страница документов                                                 */
/* ------------------------------------------------------------------ */

export function DocumentsPage() {
  const [docs, setDocs] = useState<DocItem[]>([]);
  const [customers, setCustomers] = useState<CustomerOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [kind, setKind] = useState<string>(NO);
  const [toDelete, setToDelete] = useState<DocItem | null>(null);
  const [deleting, setDeleting] = useState(false);

  const load = useCallback(async () => {
    setError("");
    try {
      const [docsRes, custRes] = await Promise.all([
        documentsApi.list({ size: 100, kind: kind === NO ? undefined : kind }),
        customersApi.list({ size: 100 }),
      ]);
      setDocs((docsRes.data?.items ?? []) as DocItem[]);
      setCustomers((custRes.data?.items ?? []) as CustomerOption[]);
    } catch (err: any) {
      setError(err.response?.data?.detail || "Не удалось загрузить документы");
    } finally {
      setLoading(false);
    }
  }, [kind]);

  useEffect(() => {
    load();
  }, [load]);

  const remove = async () => {
    if (!toDelete) return;
    setDeleting(true);
    try {
      await documentsApi.remove(toDelete.id);
      setToDelete(null);
      await load();
    } catch (err: any) {
      setError(err.response?.data?.detail || "Не удалось удалить документ");
      setToDelete(null);
    } finally {
      setDeleting(false);
    }
  };

  const attach = async (id: string, file: File) => {
    try {
      await documentsApi.attachSigned(id, file);
      await load();
    } catch (err: any) {
      setError(err.response?.data?.detail || "Не удалось приложить скан");
    }
  };

  const detach = async (doc: DocItem) => {
    try {
      await documentsApi.detachSigned(doc.id);
      await load();
    } catch (err: any) {
      setError(err.response?.data?.detail || "Не удалось открепить скан");
    }
  };

  const changeStatus = async (id: string, next: string) => {
    try {
      await documentsApi.changeStatus(id, next);
      await load();
    } catch (err: any) {
      setError(err.response?.data?.detail || "Не удалось изменить статус");
    }
  };

  if (loading) {
    return (
      <p className="py-10 text-center text-sm text-muted-foreground">Загружаем документы…</p>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Badge variant="secondary">Всего: {docs.length}</Badge>
        <div className="flex flex-wrap items-center gap-2">
          <Select value={kind} onValueChange={setKind}>
            <SelectTrigger className="h-9 w-48">
              <SelectValue placeholder="Все типы" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={NO}>Все типы</SelectItem>
              {Object.entries(KIND_LABELS).map(([value, label]) => (
                <SelectItem key={value} value={value}>
                  {label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button variant="outline" size="sm" onClick={load}>
            <RefreshCw className="mr-2 h-4 w-4" aria-hidden />
            Обновить
          </Button>
          <CompanyDialog />
          <UploadScanDialog customers={customers} onUploaded={load} />
        </div>
      </div>

      {error && (
        <p className="rounded-md bg-red-50 p-3 text-sm text-red-600">{error}</p>
      )}

      {docs.length === 0 ? (
        <p className="rounded-lg border border-dashed bg-white p-10 text-center text-sm text-muted-foreground">
          Документов пока нет. Сгенерируйте договор из сделки в разделе «Заказы»
          или загрузите подписанный скан.
        </p>
      ) : (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {docs.map((doc) => (
            <div
              key={doc.id}
              className="flex flex-col gap-2 rounded-lg border bg-white p-4 shadow-sm"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex min-w-0 items-center gap-2">
                  <FileText className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
                  <div className="min-w-0">
                    <p className="truncate text-sm font-semibold">
                      {doc.number || doc.original_name || KIND_LABELS[doc.kind]}
                    </p>
                    <p className="truncate text-xs text-muted-foreground">
                      {KIND_LABELS[doc.kind] ?? doc.kind}
                      {doc.customer ? ` · ${doc.customer.full_name}` : ""}
                    </p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setToDelete(doc)}
                  aria-label="Удалить документ"
                  className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md text-gray-300 hover:bg-red-50 hover:text-red-600"
                >
                  <Trash2 className="h-4 w-4" aria-hidden />
                </button>
              </div>

              {doc.bike_name && (
                <p className="text-xs text-muted-foreground">Байк: {doc.bike_name}</p>
              )}

              {doc.payload?.incomplete && doc.payload.incomplete.length > 0 && (
                <p className="rounded bg-amber-50 px-2 py-1 text-xs text-amber-700">
                  Черновик: не заполнено {doc.payload.incomplete.join(", ")}
                </p>
              )}

              <div className="mt-auto flex items-center justify-between gap-2 border-t pt-2">
                <div className="text-xs text-muted-foreground">
                  {fmtDate(doc.created_at)}
                  {formatBytes(doc.size) ? ` · ${formatBytes(doc.size)}` : ""}
                </div>
                <Select
                  value={doc.status}
                  onValueChange={(v) => changeStatus(doc.id, v)}
                >
                  <SelectTrigger className="h-8 w-32 text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {Object.entries(STATUS_LABELS).map(([value, label]) => (
                      <SelectItem key={value} value={value} className="text-xs">
                        {label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {doc.file_url && (
                <Button asChild variant="outline" size="sm" className="w-full">
                  <a href={`${API_URL}${doc.file_url}`} target="_blank" rel="noreferrer">
                    <Download className="mr-2 h-4 w-4" aria-hidden />
                    Открыть
                    <ExternalLink className="ml-2 h-3 w-3" aria-hidden />
                  </a>
                </Button>
              )}

              <div className="rounded-md border border-dashed p-2">
                <p className="mb-1.5 text-xs font-medium text-muted-foreground">
                  Подписанный скан
                </p>
                {doc.signed_file_url ? (
                  <div className="flex items-center gap-2">
                    <a
                      href={`${API_URL}${doc.signed_file_url}`}
                      target="_blank"
                      rel="noreferrer"
                      className="min-w-0 flex-1 truncate text-sm font-medium hover:underline"
                    >
                      {doc.signed_original_name || "скан"}
                    </a>
                    <span className="shrink-0 text-xs text-muted-foreground">
                      {fmtDate(doc.signed_at)}
                    </span>
                    <button
                      type="button"
                      onClick={() => detach(doc)}
                      aria-label="Открепить скан"
                      className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-gray-300 hover:bg-red-50 hover:text-red-600"
                    >
                      <X className="h-4 w-4" aria-hidden />
                    </button>
                  </div>
                ) : (
                  <>
                    <input
                      type="file"
                      accept="image/jpeg,image/png,image/webp,application/pdf"
                      className="w-full rounded-md border border-input bg-background p-1.5 text-xs file:mr-2 file:rounded file:border-0 file:bg-gray-100 file:px-2 file:py-1"
                      onChange={(e) => {
                        const f = e.target.files?.[0];
                        if (f) attach(doc.id, f);
                        e.target.value = "";
                      }}
                    />
                    <p className="mt-1 text-xs text-muted-foreground">
                      Приложите подписанный документ
                    </p>
                  </>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      <Dialog open={toDelete !== null} onOpenChange={(v) => !v && setToDelete(null)}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Удалить документ?</DialogTitle>
            <DialogDescription>
              {toDelete?.number || toDelete?.original_name || KIND_LABELS[toDelete?.kind ?? ""]}
              . Файл будет удалён без возможности восстановления.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setToDelete(null)} disabled={deleting}>
              Отмена
            </Button>
            <Button variant="destructive" onClick={remove} disabled={deleting}>
              {deleting ? "Удаляем…" : "Удалить"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}