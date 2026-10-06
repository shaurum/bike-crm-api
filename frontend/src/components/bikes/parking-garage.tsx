"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Bike as BikeIcon,
  Battery,
  Gauge,
  Route,
  Trash2,
  Upload,
  Plus,
  RefreshCw,
  CalendarDays,
  Wallet,
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
import { bikesApi, API_URL } from "@/lib/api";
import { formatCurrency, cn } from "@/lib/utils";

interface PriceRow {
  duration_min: number;
  duration_max: number | null;
  price: number;
  deposit: number;
}

interface BikeItem {
  id: string;
  model: string;
  frame_number: string | null;
  color: string | null;
  year: number | null;
  battery_capacity: number | null;
  max_speed: number | null;
  range_km: number | null;
  purchase_date: string | null;
  notes: string | null;
  status: string;
  is_rented: boolean;
  active_booking_status: string | null;
  photos: string[];
  prices: PriceRow[];
  branch?: { id: string; name: string } | null;
}

interface Branch {
  id: string;
  name: string;
}

const STATUS_LABELS: Record<string, string> = {
  available: "Свободен",
  reserved: "Резерв",
  rented: "В аренде",
  maintenance: "На обслуживании",
  charging: "На зарядке",
  relocation: "Перемещение",
};

function statusBadgeVariant(status: string) {
  if (status === "maintenance") return "destructive" as const;
  if (status === "available") return "default" as const;
  return "secondary" as const;
}

const WEEK = 7 * 24 * 60;
const TWO_WEEKS = 14 * 24 * 60;
const MONTH = 30 * 24 * 60;

function tierFor(prices: PriceRow[], min: number): PriceRow | undefined {
  return prices.find((p) => p.duration_min === min);
}

function priceLabel(price?: number): string {
  return price != null ? formatCurrency(price) : "—";
}

function toDateInput(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toISOString().slice(0, 10);
}

/* ------------------------------------------------------------------ */
/* Карточка байка                                                      */
/* ------------------------------------------------------------------ */

function BikePhoto({ bike, className }: { bike: BikeItem; className?: string }) {
  const src = bike.photos?.[0];
  if (!src) {
    return (
      <div
        className={cn(
          "flex items-center justify-center bg-gray-100 text-gray-300",
          className
        )}
      >
        <BikeIcon className="h-10 w-10" aria-hidden />
      </div>
    );
  }
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={`${API_URL}${src}`}
      alt={bike.model}
      className={cn("object-cover", className)}
    />
  );
}

export function BikeCard({
  bike,
  onOpen,
  onDelete,
}: {
  bike: BikeItem;
  onOpen: (id: string) => void;
  onDelete: (bike: BikeItem) => void;
}) {
  const week = tierFor(bike.prices, WEEK);
  const twoWeeks = tierFor(bike.prices, TWO_WEEKS);
  const month = tierFor(bike.prices, MONTH);

  const rented = bike.is_rented || bike.status === "rented";

  return (
    <div className="flex flex-col overflow-hidden rounded-lg border bg-white shadow-sm transition-shadow hover:shadow-md">
      <button
        type="button"
        onClick={() => onOpen(bike.id)}
        className="relative block w-full cursor-pointer text-left"
        aria-label={`Открыть карточку ${bike.model}`}
      >
        <BikePhoto bike={bike} className="h-40 w-full" />
        <span className="absolute left-2 top-2">
          <Badge variant={rented ? "secondary" : "default"}>
            {rented ? "В аренде" : STATUS_LABELS[bike.status] ?? bike.status}
          </Badge>
        </span>
      </button>

      <div className="flex flex-1 flex-col gap-2 p-3">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="truncate font-semibold leading-tight">{bike.model}</p>
            {bike.frame_number && (
              <p className="truncate text-xs text-muted-foreground">
                № {bike.frame_number}
              </p>
            )}
          </div>
          <button
            type="button"
            onClick={() => onDelete(bike)}
            aria-label="Удалить байк"
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md text-gray-300 transition-colors hover:bg-red-50 hover:text-red-600"
          >
            <Trash2 className="h-4 w-4" aria-hidden />
          </button>
        </div>

        <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
          {bike.range_km != null && (
            <span className="flex items-center gap-1">
              <Route className="h-3 w-3" aria-hidden />
              {bike.range_km} км
            </span>
          )}
          {bike.max_speed != null && (
            <span className="flex items-center gap-1">
              <Gauge className="h-3 w-3" aria-hidden />
              {bike.max_speed} км/ч
            </span>
          )}
          {bike.battery_capacity != null && (
            <span className="flex items-center gap-1">
              <Battery className="h-3 w-3" aria-hidden />
              {bike.battery_capacity} Wh
            </span>
          )}
        </div>

        <div className="mt-auto space-y-0.5 border-t pt-2 text-xs">
          <p className="flex justify-between">
            <span className="text-muted-foreground">1 неделя</span>
            <span className="font-medium">{priceLabel(week?.price)}</span>
          </p>
          <p className="flex justify-between">
            <span className="text-muted-foreground">2 недели</span>
            <span className="font-medium">{priceLabel(twoWeeks?.price)}</span>
          </p>
          <p className="flex justify-between">
            <span className="text-muted-foreground">1 месяц</span>
            <span className="font-medium">{priceLabel(month?.price)}</span>
          </p>
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Диалог байка                                                        */
/* ------------------------------------------------------------------ */

export function BikeDialog({
  bikeId,
  open,
  onOpenChange,
  branches,
  onSaved,
}: {
  bikeId: string | null;
  open: boolean;
  onOpenChange: (v: boolean) => void;
  branches: Branch[];
  onSaved: () => void;
}) {
  const [bike, setBike] = useState<BikeItem | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const [model, setModel] = useState("");
  const [frameNumber, setFrameNumber] = useState("");
  const [color, setColor] = useState("");
  const [rangeKm, setRangeKm] = useState("");
  const [maxSpeed, setMaxSpeed] = useState("");
  const [battery, setBattery] = useState("");
  const [purchaseDate, setPurchaseDate] = useState("");
  const [purchasePrice, setPurchasePrice] = useState("");
  const [notes, setNotes] = useState("");
  const [weekPrice, setWeekPrice] = useState("");
  const [twoWeekPrice, setTwoWeekPrice] = useState("");
  const [monthPrice, setMonthPrice] = useState("");
  const [deposit, setDeposit] = useState("");

  const fileRef = useRef<HTMLInputElement | null>(null);

  const hydrate = useCallback((data: BikeItem) => {
    setBike(data);
    setModel(data.model ?? "");
    setFrameNumber(data.frame_number ?? "");
    setColor(data.color ?? "");
    setRangeKm(data.range_km != null ? String(data.range_km) : "");
    setMaxSpeed(data.max_speed != null ? String(data.max_speed) : "");
    setBattery(data.battery_capacity != null ? String(data.battery_capacity) : "");
    setPurchaseDate(toDateInput(data.purchase_date));
    setNotes(data.notes ?? "");
    setWeekPrice(tierFor(data.prices, WEEK)?.price != null ? String(tierFor(data.prices, WEEK)!.price) : "");
    setTwoWeekPrice(
      tierFor(data.prices, TWO_WEEKS)?.price != null
        ? String(tierFor(data.prices, TWO_WEEKS)!.price)
        : ""
    );
    setMonthPrice(
      tierFor(data.prices, MONTH)?.price != null ? String(tierFor(data.prices, MONTH)!.price) : ""
    );
    setDeposit(data.prices?.[0]?.deposit != null ? String(data.prices[0].deposit) : "");
  }, []);

  const load = useCallback(async () => {
    if (!bikeId) return;
    setLoading(true);
    setError("");
    try {
      const res = await bikesApi.get(bikeId);
      hydrate(res.data as BikeItem);
    } catch (err: any) {
      setError(err.response?.data?.detail || "Не удалось загрузить байк");
    } finally {
      setLoading(false);
    }
  }, [bikeId, hydrate]);

  useEffect(() => {
    if (open) load();
    else {
      setBike(null);
      setError("");
    }
  }, [open, load]);

  const numOrNull = (v: string) => (v === "" ? null : Number(v));

  const toggleMaintenance = async (next: boolean) => {
    if (!bike) return;
    setSaving(true);
    setError("");
    try {
      const res = await bikesApi.update(bike.id, {
        status: next ? "maintenance" : "available",
      });
      hydrate(res.data as BikeItem);
      onSaved();
    } catch (err: any) {
      setError(err.response?.data?.detail || "Не удалось изменить статус");
    } finally {
      setSaving(false);
    }
  };

  const save = async () => {
    if (!bike) return;
    setSaving(true);
    setError("");
    try {
      const res = await bikesApi.update(bike.id, {
        model,
        frame_number: frameNumber || null,
        color: color || null,
        range_km: numOrNull(rangeKm),
        max_speed: numOrNull(maxSpeed),
        battery_capacity: numOrNull(battery),
        purchase_date: purchaseDate ? new Date(purchaseDate).toISOString() : null,
        purchase_price: numOrNull(purchasePrice),
        notes: notes || null,
        prices: {
          week_price: numOrNull(weekPrice),
          two_week_price: numOrNull(twoWeekPrice),
          month_price: numOrNull(monthPrice),
          deposit: numOrNull(deposit) ?? 0,
        },
      });
      hydrate(res.data as BikeItem);
      onSaved();
      onOpenChange(false);
    } catch (err: any) {
      setError(err.response?.data?.detail || "Не удалось сохранить");
    } finally {
      setSaving(false);
    }
  };

  const uploadPhoto = async (file: File) => {
    if (!bike) return;
    setSaving(true);
    setError("");
    try {
      const res = await bikesApi.uploadPhoto(bike.id, file);
      hydrate(res.data as BikeItem);
      onSaved();
    } catch (err: any) {
      setError(err.response?.data?.detail || "Не удалось загрузить фото");
    } finally {
      setSaving(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const rented = bike?.is_rented || bike?.status === "rented";
  const isMaintenance = bike?.status === "maintenance";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[92vh] flex-col gap-0 overflow-hidden p-0 sm:max-w-2xl">
        <div className="flex shrink-0 items-start justify-between gap-3 border-b px-5 pb-4 pt-5">
          <DialogHeader>
            <DialogTitle>{bike?.model || "Байк"}</DialogTitle>
            <DialogDescription>
              {rented
                ? "Байк в аренде — статус берётся из CRM"
                : "Карточка устройства гаража"}
            </DialogDescription>
          </DialogHeader>
          {bike && (
            <Badge variant={rented ? "secondary" : "default"} className="shrink-0">
              {rented ? "В аренде" : STATUS_LABELS[bike.status] ?? bike.status}
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

          {bike && !loading && (
            <>
              <div className="flex gap-4">
                <div className="w-40 shrink-0 overflow-hidden rounded-lg">
                  <BikePhoto bike={bike} className="h-32 w-40" />
                </div>
                <div className="flex-1 space-y-2">
                  <input
                    ref={fileRef}
                    type="file"
                    accept="image/jpeg,image/png,image/webp,image/gif"
                    className="hidden"
                    onChange={(e) => {
                      const f = e.target.files?.[0];
                      if (f) uploadPhoto(f);
                    }}
                  />
                  <Button
                    variant="outline"
                    size="sm"
                    className="w-full"
                    disabled={saving}
                    onClick={() => fileRef.current?.click()}
                  >
                    <Upload className="mr-2 h-4 w-4" aria-hidden />
                    Загрузить фото
                  </Button>
                  <p className="text-xs text-muted-foreground">
                    JPG, PNG, WEBP или GIF до 8 МБ
                  </p>
                </div>
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-1.5 sm:col-span-2">
                  <label className="text-sm font-medium" htmlFor="b-model">
                    Модель
                  </label>
                  <Input
                    id="b-model"
                    value={model}
                    onChange={(e) => setModel(e.target.value)}
                  />
                </div>

                <div className="space-y-1.5">
                  <label className="text-sm font-medium" htmlFor="b-frame">
                    Номер рамы
                  </label>
                  <Input
                    id="b-frame"
                    value={frameNumber}
                    onChange={(e) => setFrameNumber(e.target.value)}
                  />
                </div>

                <div className="space-y-1.5">
                  <label className="text-sm font-medium" htmlFor="b-color">
                    Цвет
                  </label>
                  <Input
                    id="b-color"
                    value={color}
                    onChange={(e) => setColor(e.target.value)}
                  />
                </div>

                <div className="space-y-1.5">
                  <label className="text-sm font-medium" htmlFor="b-range">
                    Запас хода, км
                  </label>
                  <Input
                    id="b-range"
                    type="number"
                    value={rangeKm}
                    onChange={(e) => setRangeKm(e.target.value)}
                  />
                </div>

                <div className="space-y-1.5">
                  <label className="text-sm font-medium" htmlFor="b-speed">
                    Макс. скорость, км/ч
                  </label>
                  <Input
                    id="b-speed"
                    type="number"
                    value={maxSpeed}
                    onChange={(e) => setMaxSpeed(e.target.value)}
                  />
                </div>

                <div className="space-y-1.5">
                  <label className="flex items-center gap-1.5 text-sm font-medium" htmlFor="b-batt">
                    <Battery className="h-3.5 w-3.5 text-muted-foreground" aria-hidden />
                    Аккумулятор, Wh
                  </label>
                  <Input
                    id="b-batt"
                    type="number"
                    value={battery}
                    onChange={(e) => setBattery(e.target.value)}
                  />
                </div>

                <div className="space-y-1.5">
                  <label className="flex items-center gap-1.5 text-sm font-medium" htmlFor="b-pdate">
                    <CalendarDays className="h-3.5 w-3.5 text-muted-foreground" aria-hidden />
                    Дата покупки
                  </label>
                  <Input
                    id="b-pdate"
                    type="date"
                    value={purchaseDate}
                    onChange={(e) => setPurchaseDate(e.target.value)}
                  />
                </div>

                <div className="space-y-1.5">
                  <label className="flex items-center gap-1.5 text-sm font-medium" htmlFor="b-pprice">
                    <Wallet className="h-3.5 w-3.5 text-muted-foreground" aria-hidden />
                    Цена закупки, ₽
                  </label>
                  <Input
                    id="b-pprice"
                    type="number"
                    value={purchasePrice}
                    onChange={(e) => setPurchasePrice(e.target.value)}
                  />
                </div>

                <div className="space-y-1.5 sm:col-span-2">
                  <label className="text-sm font-medium">Статус</label>
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant={statusBadgeVariant(bike.status)}>
                      {STATUS_LABELS[bike.status] ?? bike.status}
                    </Badge>
                    <Button
                      variant={isMaintenance ? "default" : "outline"}
                      size="sm"
                      disabled={saving}
                      onClick={() => toggleMaintenance(!isMaintenance)}
                    >
                      {isMaintenance ? "Снять с обслуживания" : "На обслуживание"}
                    </Button>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    Статус переключается сам по этапу воронки у связанной сделки.
                    Отсюда доступно только обслуживание.
                  </p>
                </div>
              </div>

              <div className="space-y-3 rounded-lg border p-3">
                <p className="text-sm font-semibold">Прайс</p>
                <div className="grid gap-3 sm:grid-cols-4">
                  <div className="space-y-1.5">
                    <label className="text-xs font-medium" htmlFor="p-week">
                      1 неделя, ₽
                    </label>
                    <Input
                      id="p-week"
                      type="number"
                      value={weekPrice}
                      onChange={(e) => setWeekPrice(e.target.value)}
                      placeholder="6500"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <label className="text-xs font-medium" htmlFor="p-2week">
                      2 недели, ₽
                    </label>
                    <Input
                      id="p-2week"
                      type="number"
                      value={twoWeekPrice}
                      onChange={(e) => setTwoWeekPrice(e.target.value)}
                      placeholder="12000"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <label className="text-xs font-medium" htmlFor="p-month">
                      1 месяц, ₽
                    </label>
                    <Input
                      id="p-month"
                      type="number"
                      value={monthPrice}
                      onChange={(e) => setMonthPrice(e.target.value)}
                      placeholder="20000"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <label className="text-xs font-medium" htmlFor="p-deposit">
                      Залог, ₽
                    </label>
                    <Input
                      id="p-deposit"
                      type="number"
                      value={deposit}
                      onChange={(e) => setDeposit(e.target.value)}
                    />
                  </div>
                </div>
              </div>

              <div className="space-y-1.5">
                <label className="text-sm font-medium" htmlFor="b-notes">
                  Описание
                </label>
                <textarea
                  id="b-notes"
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  rows={3}
                  placeholder="Состояние, особенности, комплектация"
                  className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                />
              </div>
            </>
          )}
        </div>

        <div className="shrink-0 border-t bg-white px-5 py-3">
          <div className="flex items-center justify-end">
            <Button onClick={save} disabled={saving || !bike}>
              {saving ? "Сохраняем…" : "Сохранить"}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

/* ------------------------------------------------------------------ */
/* Добавление байка                                                    */
/* ------------------------------------------------------------------ */

function AddBikeDialog({
  branches,
  onCreated,
}: {
  branches: Branch[];
  onCreated: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [model, setModel] = useState("");
  const [frameNumber, setFrameNumber] = useState("");
  const [weekPrice, setWeekPrice] = useState("");
  const [twoWeekPrice, setTwoWeekPrice] = useState("");
  const [monthPrice, setMonthPrice] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!model.trim()) {
      setError("Укажите модель");
      return;
    }
    const branch = branches[0]?.id;
    if (!branch) {
      setError("В системе нет филиала");
      return;
    }
    setSaving(true);
    setError("");
    try {
      await bikesApi.create({
        branch_id: branch,
        model: model.trim(),
        frame_number: frameNumber.trim() || null,
        prices: {
          week_price: weekPrice ? Number(weekPrice) : null,
          two_week_price: twoWeekPrice ? Number(twoWeekPrice) : null,
          month_price: monthPrice ? Number(monthPrice) : null,
          deposit: 0,
        },
      });
      setOpen(false);
      setModel("");
      setFrameNumber("");
      setWeekPrice("");
      setTwoWeekPrice("");
      setMonthPrice("");
      onCreated();
    } catch (err: any) {
      setError(err.response?.data?.detail || "Не удалось добавить байк");
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
          Добавить байк
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Новый байк</DialogTitle>
          <DialogDescription>
            Модель и номер рамы обязательны, остальное заполните в карточке.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={submit} className="space-y-3">
          <div className="space-y-1.5">
            <label className="text-sm font-medium" htmlFor="nb-model">
              Модель
            </label>
            <Input
              id="nb-model"
              value={model}
              onChange={(e) => setModel(e.target.value)}
              placeholder="Maikaline U2"
              required
            />
          </div>

          <div className="space-y-1.5">
            <label className="text-sm font-medium" htmlFor="nb-frame">
              Номер рамы
            </label>
            <Input
              id="nb-frame"
              value={frameNumber}
              onChange={(e) => setFrameNumber(e.target.value)}
              placeholder="MK-U2-0002"
            />
          </div>

          <div className="grid gap-3 sm:grid-cols-3">
            <div className="space-y-1.5">
              <label className="text-xs font-medium" htmlFor="nb-week">
                1 неделя, ₽
              </label>
              <Input
                id="nb-week"
                type="number"
                value={weekPrice}
                onChange={(e) => setWeekPrice(e.target.value)}
                placeholder="6500"
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-xs font-medium" htmlFor="nb-2week">
                2 недели, ₽
              </label>
              <Input
                id="nb-2week"
                type="number"
                value={twoWeekPrice}
                onChange={(e) => setTwoWeekPrice(e.target.value)}
                placeholder="12000"
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-xs font-medium" htmlFor="nb-month">
                1 месяц, ₽
              </label>
              <Input
                id="nb-month"
                type="number"
                value={monthPrice}
                onChange={(e) => setMonthPrice(e.target.value)}
                placeholder="20000"
              />
            </div>
          </div>

          {error && (
            <p className="rounded-md bg-red-50 p-2 text-sm text-red-600">{error}</p>
          )}

          <DialogFooter className="justify-end">
            <Button type="submit" disabled={saving}>
              {saving ? "Добавляем…" : "Добавить"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/* ------------------------------------------------------------------ */
/* Страница парковки                                                  */
/* ------------------------------------------------------------------ */

export function ParkingGarage() {
  const [bikes, setBikes] = useState<BikeItem[]>([]);
  const [branches, setBranches] = useState<Branch[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [toDelete, setToDelete] = useState<BikeItem | null>(null);
  const [deleting, setDeleting] = useState(false);

  const load = useCallback(async () => {
    setError("");
    try {
      const [bikesRes, brRes] = await Promise.all([
        bikesApi.list({ size: 100, search: search || undefined }),
        bikesApi.branches(),
      ]);
      setBikes((bikesRes.data?.items ?? []) as BikeItem[]);
      setBranches((brRes.data?.items ?? []) as Branch[]);
    } catch (err: any) {
      setError(err.response?.data?.detail || "Не удалось загрузить гараж");
    } finally {
      setLoading(false);
    }
  }, [search]);

  useEffect(() => {
    const t = setTimeout(load, search ? 300 : 0);
    return () => clearTimeout(t);
  }, [load, search]);

  const confirmDelete = async () => {
    if (!toDelete) return;
    setDeleting(true);
    try {
      await bikesApi.remove(toDelete.id);
      setToDelete(null);
      await load();
    } catch (err: any) {
      setError(err.response?.data?.detail || "Не удалось удалить байк");
      setToDelete(null);
    } finally {
      setDeleting(false);
    }
  };

  const rentedCount = bikes.filter((b) => b.is_rented).length;

  if (loading) {
    return (
      <p className="py-10 text-center text-sm text-muted-foreground">Загружаем гараж…</p>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Badge variant="secondary">Всего: {bikes.length}</Badge>
          <Badge>Свободно: {bikes.length - rentedCount}</Badge>
          <Badge variant="secondary">В аренде: {rentedCount}</Badge>
        </div>
        <div className="flex items-center gap-2">
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Поиск по модели или раме"
            className="h-9 w-52"
          />
          <Button variant="outline" size="sm" onClick={load}>
            <RefreshCw className="mr-2 h-4 w-4" aria-hidden />
            Обновить
          </Button>
          <AddBikeDialog branches={branches} onCreated={load} />
        </div>
      </div>

      {error && (
        <p className="rounded-md bg-red-50 p-3 text-sm text-red-600">{error}</p>
      )}

      {bikes.length === 0 ? (
        <p className="rounded-lg border border-dashed bg-white p-10 text-center text-sm text-muted-foreground">
          Гараж пуст — добавьте первый байк
        </p>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {bikes.map((bike) => (
            <BikeCard
              key={bike.id}
              bike={bike}
              onOpen={setSelectedId}
              onDelete={setToDelete}
            />
          ))}
        </div>
      )}

      <BikeDialog
        bikeId={selectedId}
        open={selectedId !== null}
        onOpenChange={(v) => {
          if (!v) setSelectedId(null);
        }}
        branches={branches}
        onSaved={load}
      />

      <Dialog open={toDelete !== null} onOpenChange={(v) => !v && setToDelete(null)}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Удалить байк?</DialogTitle>
            <DialogDescription>
              {toDelete?.model}
              {toDelete?.frame_number ? ` · № ${toDelete.frame_number}` : ""}. Байк
              уйдёт в архив, записи о нём в бронях сохранятся.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setToDelete(null)} disabled={deleting}>
              Отмена
            </Button>
            <Button variant="destructive" onClick={confirmDelete} disabled={deleting}>
              {deleting ? "Удаляем…" : "Удалить"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}