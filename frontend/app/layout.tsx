import type { Metadata } from "next";
import { Fraunces, Literata, Mukta_Mahee } from "next/font/google";
import "./globals.css";
import { SiteHeader } from "@/components/SiteHeader";
import { SiteFooter } from "@/components/SiteFooter";

const fraunces = Fraunces({
  subsets: ["latin"],
  variable: "--font-display",
  weight: ["400", "500", "600", "700"],
  style: ["normal", "italic"],
});

const literata = Literata({
  subsets: ["latin"],
  variable: "--font-body",
  weight: ["400", "500", "600", "700"],
});

const muktaMahee = Mukta_Mahee({
  subsets: ["gurmukhi", "latin"],
  variable: "--font-gurmukhi",
  weight: ["400", "500", "600", "700"],
});

export const metadata: Metadata = {
  title: "Sach Khoj (ਸੱਚ ਖੋਜ) — Check it against Gurbani before you share it",
  description:
    "Saw a reel or post quoting Guru Sahib? Paste the link. Sach Khoj checks claims about Gurbani, Sikh history and Rehat against Sri Guru Granth Sahib Ji and trusted sources, and shows you the Ang.",
  openGraph: {
    title: "Sach Khoj (ਸੱਚ ਖੋਜ)",
    description:
      "Check reels, posts and forwards about Sikhi against Gurbani and trusted sources. Every answer comes with the Ang.",
    type: "website",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${fraunces.variable} ${literata.variable} ${muktaMahee.variable}`}>
      <body>
        <div className="atmosphere" aria-hidden="true" />
        <SiteHeader />
        <main>{children}</main>
        <SiteFooter />
      </body>
    </html>
  );
}
