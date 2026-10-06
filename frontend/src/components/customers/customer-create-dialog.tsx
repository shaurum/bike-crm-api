"use client";

import { useEffect, useState } from "react";
import { Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { customersApi } from "@/lib/api";

export interface CreatedCustomer {
  id: string;
  full_name: string;
  phone: string;
  email: string | null;
}

const DOC_TYPES = [
  { value: "passport_rf", label: "Паспорт РФ" },
  { value: "foreign_passport", label: "Загранпаспорт" },
  { value: "residence_permit", label: "РВП / ВНЖ" },
  { value: "id_card", label: "ID-карта" },
  { value: "driver_license", label: "Вод. удостоверение" },
  { value: "other", label: "Другой документ" },
];

const RF_EXAMPLES: Record<string, string> = {
  series: "45 12",
  number: "123456",
  country: "Россия",
};

export function CustomerCreateDialog({
  open,
  onOpenChange,
  defaultName,
  defaultPhone,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  defaultName?: string;
  defaultPhone?: string;
  onCreated: (customer: CreatedCustomer) => void;
}) {
  const [fullName, setFullName] = useState(defaultName ?? "");
  const [phone, setPhone] = useState(defaultPhone ?? "");
  const [email, setEmail] = useState("");
  const [docType, setDocType] = useState("passport_rf");
  const [country, setCountry] = useState(RF_EXAMPLES.country);
  const [birthDate, setBirthDate] = useState("");
  const [series, setSeries] = useState("");
  const [number, setNumber] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open) {
      setFullName(defaultName ?? "");
      setPhone(defaultPhone ?? "");
      setError("");
    }
  }, [open, defaultName, defaultPhone]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError("");
    try {
      const res = await customersApi.create({
        full_name: fullName.trim(),
        phone: phone.trim(),
        email: email.trim() || null,
        document_type: docType,
        country: country.trim() || RF_EXAMPLES.country,
        birth_date: birthDate || null,
        passport_series: series.trim() || null,
        passport_number: number.trim() || null,
      });
      onCreated(res.data as CreatedCustomer);
      onOpenChange(false);
      setFullName("");
      setPhone("");
      setEmail("");
      setBirthDate("");
      setSeries("");
      setNumber("");
    } catch (err: any) {
      setError(err.response?.data?.detail || "Не удалось создать клиента");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Plus className="h-5 w-5" aria-hidden />
            Новый клиент
          </DialogTitle>
          <DialogDescription>
            Паспортные данные и сканы заполните позже в карточке клиента.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={submit} className="space-y-3">
          <div className="space-y-1.5">
            <label className="text-sm font-medium" htmlFor="cc-name">
              ФИО
            </label>
            <Input
              id="cc-name"
              name="name"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              required
              autoFocus
            />
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <label className="text-sm font-medium" htmlFor="cc-phone">
                Телефон
              </label>
              <Input
                id="cc-phone"
                name="tel"
                type="tel"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                required
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-sm font-medium" htmlFor="cc-email">
                Email
              </label>
              <Input
                id="cc-email"
                name="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <label className="text-xs font-medium" htmlFor="cc-doctype">
                Тип документа
              </label>
              <Select value={docType} onValueChange={setDocType}>
                <SelectTrigger id="cc-doctype">
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
              <label className="text-xs font-medium" htmlFor="cc-country">
                Страна
              </label>
              <Input
                id="cc-country"
                value={country}
                onChange={(e) => setCountry(e.target.value)}
                placeholder={RF_EXAMPLES.country}
              />
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-3">
            <div className="space-y-1.5">
              <label className="text-xs font-medium" htmlFor="cc-birth">
                Дата рождения
              </label>
              <Input
                id="cc-birth"
                type="date"
                value={birthDate}
                onChange={(e) => setBirthDate(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-xs font-medium" htmlFor="cc-series">
                Серия
              </label>
              <Input
                id="cc-series"
                value={series}
                onChange={(e) => setSeries(e.target.value)}
                placeholder={RF_EXAMPLES.series}
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-xs font-medium" htmlFor="cc-number">
                Номер
              </label>
              <Input
                id="cc-number"
                value={number}
                onChange={(e) => setNumber(e.target.value)}
                placeholder={RF_EXAMPLES.number}
              />
            </div>
          </div>

          {error && (
            <p className="rounded-md bg-red-50 p-2 text-sm text-red-600">{error}</p>
          )}

          <DialogFooter className="justify-end">
            <Button type="submit" disabled={saving}>
              {saving ? "Создаём…" : "Создать клиента"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}