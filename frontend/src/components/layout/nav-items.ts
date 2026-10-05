import {
  LayoutDashboard,
  ClipboardList,
  Users,
  Bike,
  FileText,
  ListChecks,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
}

export const NAV_ITEMS: NavItem[] = [
  { href: "/", label: "Панель управления", icon: LayoutDashboard },
  { href: "/orders", label: "Заказы", icon: ClipboardList },
  { href: "/customers", label: "Клиенты", icon: Users },
  { href: "/parking", label: "Парковка", icon: Bike },
  { href: "/documents", label: "Документы", icon: FileText },
  { href: "/tasks", label: "Задачи", icon: ListChecks },
];