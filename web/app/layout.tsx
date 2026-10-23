import type { Metadata, Viewport } from "next";
import { Assistant, Rubik } from "next/font/google";
import "./globals.css";

const assistant = Assistant({ variable: "--font-assistant", subsets: ["hebrew", "latin"], weight: ["400", "600", "700", "800"] });
const rubik = Rubik({ variable: "--font-rubik", subsets: ["hebrew", "latin"], weight: ["500", "700", "800"] });

export const metadata: Metadata = {
  title: "FreeRise",
  description: "ניהול כספי משק הבית",
  manifest: "/manifest.webmanifest",
  appleWebApp: { title: "FreeRise", capable: true },
};

export const viewport: Viewport = { themeColor: "#fbf7f0" };

// Blocking pre-paint script: applies the saved theme and the matching theme-color meta.
const THEME_SCRIPT = `try{var t=localStorage.getItem("freerise-theme");var h=document.documentElement;if(t==="light"||t==="dark"){h.setAttribute("data-theme",t);var m=document.querySelector('meta[name="theme-color"]');if(!m){m=document.createElement("meta");m.name="theme-color";document.head.appendChild(m)}m.content=t==="dark"?"#171512":"#fbf7f0"}}catch(e){}`;

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="he" dir="rtl" className={`${assistant.variable} ${rubik.variable} h-full antialiased`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body className="min-h-full font-sans">{children}</body>
    </html>
  );
}
