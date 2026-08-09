import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "European TCG Index",
  description: "EU-first listing-price benchmarks derived from Cardmarket daily downloads."
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
