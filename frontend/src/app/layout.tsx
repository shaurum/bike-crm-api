import type { Metadata } from "next";
import "@fontsource/montserrat/cyrillic-400.css";
import "@fontsource/montserrat/latin-400.css";
import "@fontsource/montserrat/cyrillic-500.css";
import "@fontsource/montserrat/latin-500.css";
import "@fontsource/montserrat/cyrillic-600.css";
import "@fontsource/montserrat/latin-600.css";
import "@fontsource/montserrat/cyrillic-700.css";
import "@fontsource/montserrat/latin-700.css";
import "@fontsource/unbounded/cyrillic-700.css";
import "@fontsource/unbounded/latin-700.css";
import "@fontsource/unbounded/cyrillic-800.css";
import "@fontsource/unbounded/latin-800.css";
import "./globals.css";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: "ВЖУХ CRM",
  description: "CRM-система для управления прокатом электробайков",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ru" suppressHydrationWarning>
      <body className="font-sans antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}