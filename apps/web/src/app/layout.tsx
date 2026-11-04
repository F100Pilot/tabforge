import type { Metadata } from "next";
import { Suspense } from "react";
import { Geist, Geist_Mono } from "next/font/google";
import { SideNav } from "@/components/side-nav";
import "./globals.css";

const geist = Geist({ subsets: ["latin"], variable: "--font-geist", display: "swap" });
const geistMono = Geist_Mono({ subsets: ["latin"], variable: "--font-geist-mono", display: "swap" });

export const metadata: Metadata = {
  title: "TabForge",
  description: "Tablaturas interativas geradas a partir de áudio com IA",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="pt" className={`${geist.variable} ${geistMono.variable}`}>
      <body>
        <div className="shell">
          <Suspense fallback={<div className="sidenav" />}>
            <SideNav />
          </Suspense>
          <main className="content">{children}</main>
        </div>
      </body>
    </html>
  );
}
