"use client";

import { Mail, MessageCircle, MessageSquare, Phone } from "lucide-react";

const CHANNEL_COLORS: Record<string, string> = {
  telegram: "#229ED9",
  avito: "#0EA5E9",
  email: "#F97316",
  phone: "#16A34A",
  whatsapp: "#25D366",
  vk: "#0077FF",
  internal: "#64748B",
};

function Badge({ letter, color, className }: { letter: string; color: string; className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden focusable="false">
      <rect width="24" height="24" rx="6" fill={color} />
      <text
        x="12"
        y="16.5"
        textAnchor="middle"
        fontSize={letter.length > 1 ? 9 : 13}
        fontWeight="700"
        fill="#fff"
        fontFamily="inherit"
      >
        {letter}
      </text>
    </svg>
  );
}

/** Иконка канала связи: цвет и глиф по типу (авито, почта, телеграм и т.д.). */
export function ChannelIcon({
  channel,
  className = "h-4 w-4",
}: {
  channel: string;
  className?: string;
}) {
  const color = CHANNEL_COLORS[channel] ?? CHANNEL_COLORS.internal;

  switch (channel) {
    case "email":
      return <Mail className={className} style={{ color }} aria-hidden />;
    case "phone":
      return <Phone className={className} style={{ color }} aria-hidden />;
    case "whatsapp":
      return <MessageCircle className={className} style={{ color }} aria-hidden />;
    case "internal":
      return <MessageSquare className={className} style={{ color }} aria-hidden />;
    case "telegram":
      return (
        <svg viewBox="0 0 24 24" className={className} fill={color} aria-hidden focusable="false">
          <path d="M9.78 18.65l.28-4.23 7.68-6.92c.34-.31-.07-.46-.52-.19L7.74 13.3 3.64 12c-.88-.25-.89-.86.2-1.3l15.97-6.16c.73-.33 1.43.18 1.15 1.3l-2.72 12.81c-.19.91-.74 1.13-1.5.71L12.6 16.3l-1.99 1.93c-.23.23-.42.42-.83.42z" />
        </svg>
      );
    case "avito":
      return <Badge letter="А" color={color} className={className} />;
    case "vk":
      return <Badge letter="VK" color={color} className={className} />;
    default:
      return <MessageSquare className={className} style={{ color }} aria-hidden />;
  }
}
