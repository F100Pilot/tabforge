import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "TabForge",
  description: "Tablaturas interativas geradas a partir de áudio com IA",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="pt">
      <body>{children}</body>
    </html>
  );
}
