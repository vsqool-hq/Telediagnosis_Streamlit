import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import Sidebar from "@/components/Sidebar";
import AuthGate from "@/components/AuthGate";

const inter = Inter({ subsets: ["latin", "latin-ext"], variable: "--font-inter" });

export const metadata: Metadata = {
  title: "Automatyzator Rozliczeń Medycznych",
  description: "Telediagnosis — rozliczenia, weryfikacja i statystyki",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pl" className={inter.variable}>
      <body>
        <AuthGate>
          <div className="flex min-h-screen">
            <Sidebar />
            <main className="flex-1 overflow-x-hidden px-6 py-8 md:px-10">
              <div className="mx-auto max-w-6xl">{children}</div>
            </main>
          </div>
        </AuthGate>
      </body>
    </html>
  );
}
