import Link from "next/link";

export type BreadcrumbItem = {
  label: string;
  href?: string;
};

export function Breadcrumbs({ items }: { items: BreadcrumbItem[] }) {
  return (
    <nav aria-label="Breadcrumb" className="mb-5 text-xs text-paper/50">
      <ol className="flex flex-wrap items-center gap-2">
        {items.map((item, index) => (
          <li key={`${item.label}-${index}`} className="flex items-center gap-2">
            {index > 0 ? <span aria-hidden="true">&gt;</span> : null}
            {item.href ? (
              <Link href={item.href} className="hover:text-paper">{item.label}</Link>
            ) : (
              <span aria-current="page" className="text-paper/70">{item.label}</span>
            )}
          </li>
        ))}
      </ol>
    </nav>
  );
}
