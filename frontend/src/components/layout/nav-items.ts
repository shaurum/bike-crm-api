import {
  LayoutDashboard,
  ClipboardList,
  Users,
  Bike,
  FileText,
  MessageSquare,
  ListChecks,
  BookOpen,
  Settings,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  /** Показывать только роли admin. */
  adminOnly?: boolean;
}

export const NAV_ITEMS: NavItem[] = [
  { href: "/", label: "Панель управления", icon: LayoutDashboard },
  { href: "/orders", label: "Заказы", icon: ClipboardList },
  { href: "/customers", label: "Клиенты", icon: Users },
  { href: "/parking", label: "Парковка", icon: Bike },
  { href: "/documents", label: "Документы", icon: FileText },
  { href: "/messages", label: "Сообщения", icon: MessageSquare },
  { href: "/tasks", label: "Задачи", icon: ListChecks },
  { href: "/knowledge", label: "База знаний", icon: BookOpen },
  { href: "/settings", label: "Настройки", icon: Settings },
];