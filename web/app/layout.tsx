import { ServiceWorkerRegister } from "@/components/offline/ServiceWorkerRegister";
import { HtmlLangSync } from "@/components/layout/HtmlLangSync";
import { WebVitalsReporter } from "@/components/layout/WebVitalsReporter";
import { QueryProvider } from "@/providers/QueryProvider";
import { LocaleProvider } from "@/providers/LocaleProvider";
import { fontClassNames } from "@/lib/fonts";
import { themeInitScript } from "@/lib/theme";
import { NuqsAdapter } from "nuqs/adapters/next/app";
import "./globals.css";
import type { Metadata, Viewport } from "next";
import Script from "next/script";

export const metadata: Metadata = {
  title: "Spark Ops",
  description: "Factory knowledge chat — on-prem AI",
  manifest: "/manifest.json",
  applicationName: "Spark Ops",
  icons: {
    icon: [
      { url: "/icons/icon-32.png", sizes: "32x32", type: "image/png" },
      { url: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
      { url: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
    ],
    apple: [{ url: "/icons/apple-touch-icon.png", sizes: "180x180", type: "image/png" }],
  },
  appleWebApp: {
    title: "Spark Ops",
    statusBarStyle: "default",
  },
  other: {
    "mobile-web-app-capable": "yes",
  },
};

export const viewport: Viewport = {
  themeColor: "#0ea5e9",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="th" data-theme="dark" suppressHydrationWarning className={`dark ${fontClassNames}`}>
      <head>
        <link rel="icon" type="image/png" sizes="32x32" href="/icons/icon-32.png" />
        <link rel="icon" type="image/png" sizes="192x192" href="/icons/icon-192.png" />
        <link rel="apple-touch-icon" href="/icons/apple-touch-icon.png" />
        <Script id="spark-theme-init" strategy="beforeInteractive">
          {themeInitScript}
        </Script>
      </head>
      <body className="font-sans antialiased">
        <HtmlLangSync />
        <ServiceWorkerRegister />
        <WebVitalsReporter />
        <NuqsAdapter>
          <LocaleProvider>
            <QueryProvider>{children}</QueryProvider>
          </LocaleProvider>
        </NuqsAdapter>
      </body>
    </html>
  );
}
