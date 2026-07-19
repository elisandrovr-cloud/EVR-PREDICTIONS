import type { Metadata } from "next";

import "./globals.css";
import { Sidebar } from "@/components/layout/sidebar";
import { Topbar } from "@/components/layout/topbar";
import { Providers } from "@/lib/providers";

export const metadata: Metadata = {
  title: "EVR MLB AI PRO — Terminal de Apuestas MLB",
  description:
    "Plataforma de análisis MLB impulsada por IA: probabilidades reales, value bets, props y parlays generados por un ensemble auto-calibrado.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es">
      <body>
        <Providers>
          <Sidebar />
          <div className="md:pl-52">
            <Topbar />
            <main className="mx-auto max-w-7xl p-4">{children}</main>
          </div>
        </Providers>
      </body>
    </html>
  );
}
