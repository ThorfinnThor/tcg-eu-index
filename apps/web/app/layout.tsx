import type { Metadata } from "next";
import Link from "next/link";
import { getSiteUrl } from "@/lib/site";
import "./globals.css";

const siteUrl = getSiteUrl();

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  title: {
    default: "European TCG Index",
    template: "%s | European TCG Index"
  },
  description: "EU-first listing-price benchmarks for major trading card games.",
  applicationName: "European TCG Index",
  authors: [{ name: "European TCG Index" }],
  category: "finance",
  openGraph: {
    type: "website",
    siteName: "European TCG Index",
    title: "European TCG Index",
    description: "Transparent European TCG listing-price benchmarks with methodology and data-quality disclosures.",
    url: siteUrl
  },
  twitter: { card: "summary", title: "European TCG Index" }
};

const nav = [
  ["Overview", "/"],
  ["Methodology", "/methodology"],
  ["Reports", "/reports"],
  ["Portfolio", "/portfolio"],
  ["Data quality", "/data-quality"]
];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen font-sans antialiased">
        <header className="border-b border-line bg-ink/95">
          <div className="mx-auto flex max-w-7xl flex-col gap-3 px-4 py-4 sm:flex-row sm:items-center sm:justify-between">
            <Link href="/" className="text-lg font-semibold tracking-normal text-paper">
              European TCG Index
            </Link>
            <nav className="flex flex-wrap gap-2 text-sm text-paper/70">
              {nav.map(([label, href]) => (
                <Link key={href} href={href} className="chip hover:border-amber hover:text-paper">
                  {label}
                </Link>
              ))}
            </nav>
          </div>
        </header>
        <main>{children}</main>
      </body>
    </html>
  );
}
