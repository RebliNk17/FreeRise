import type { Metadata, Viewport } from "next";
import localFont from "next/font/local";
import "./globals.css";

// Self-hosted (Hebrew + Latin subsets of the Google Fonts variable files, OFL) so builds never
// depend on fonts.googleapis.com. Licenses in ./fonts.
const assistant = localFont({ src: "./fonts/Assistant.woff2", variable: "--font-assistant", weight: "200 800" });
const rubik = localFont({ src: "./fonts/Rubik.woff2", variable: "--font-rubik", weight: "300 900" });

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
