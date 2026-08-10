import Link from "next/link";
import { getPageDefinition, isIndexable } from "@/lib/seo";

const relationshipLabels = {
  parent: "Overview",
  child: "Index",
  related: "Related",
  comparison: "Compare",
  next_step: "Next step"
};

export function RelatedPages({ definitionId }: { definitionId: string }) {
  const definition = getPageDefinition(definitionId);
  if (!definition) return null;
  const links = definition.relationships
    .map((relationship) => ({ relationship, target: getPageDefinition(relationship.targetId) }))
    .filter((item) => item.target && isIndexable(item.target));
  if (links.length === 0) return null;

  return (
    <nav aria-label="Related pages" className="mt-8 border-t border-line pt-5">
      <h2 className="text-sm font-semibold text-paper">Related pages</h2>
      <div className="mt-3 flex flex-wrap gap-x-5 gap-y-3 text-sm">
        {links.map(({ relationship, target }) => target ? (
          <Link key={`${relationship.type}-${target.id}`} href={target.canonical} className="group text-paper/65 hover:text-paper">
            <span className="mr-2 text-xs text-paper/40">{relationshipLabels[relationship.type]}</span>
            <span className="text-amber group-hover:text-paper">{target.linkLabel}</span>
          </Link>
        ) : null)}
      </div>
    </nav>
  );
}
