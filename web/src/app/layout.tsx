import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata: Metadata = {
  title: "EXONAUT // Autonomous Exploration System",
  description:
    "Mission control for EXONAUT: adaptive risk-aware autonomy for robotic exploration of uncertain extraterrestrial terrain.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className="bg-[#07090d] text-slate-200 antialiased">{children}</body>
    </html>
  );
}
