import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { AppProviders } from "@/app/providers";
import { themeInitScript } from "@/lib/theme";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-sans",
});

export const metadata: Metadata = {
  title: "SOS Affiliate · Console",
  description: "La console SOS Affiliate: rete dei Digital Ambassador, licenze, Pack, MamiCash e bonus BC, BD e BM.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="it" className={`${inter.variable}`} data-theme="dark" data-surface="dark" suppressHydrationWarning>
      <head>
        {/* Applies the stored theme before hydration to avoid a flash. */}
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
      </head>
      <body className="min-h-screen antialiased">
        <AppProviders>{children}</AppProviders>
      </body>
    </html>
  );
}
