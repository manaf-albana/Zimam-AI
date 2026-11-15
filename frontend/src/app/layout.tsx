import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "زِمَام الذكي | Zimam-AI - المنظومة الذاتية لحواسيب الذكاء الاصطناعي",
  description: "المنظومة الذاتية لأتمتة الأنظمة وتطبيقات الويب بحواسيب الذكاء الاصطناعي والاستدلال الحتمي (Zimam Deterministic GUI Runtime)",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ar" dir="rtl">
      <body className="antialiased bg-[#030712] text-slate-100 min-h-screen">
        {children}
      </body>
    </html>
  );
}
