import type { Metadata } from "next";
import pageDefinitionsJson from "@/data-config/seo/page-definitions.json";

export type SeoRelationshipType = "parent" | "child" | "related" | "comparison" | "next_step";

export type SeoPageDefinition = {
  id: string;
  linkLabel: string;
  slug: string;
  keywordId: string;
  locale: string;
  intent: string;
  cluster: string;
  template: string;
  filters: Record<string, string>;
  minimumResults: number;
  minimumDataCompleteness: number;
  minimumInsights: number;
  canonical: string;
  relationships: Array<{ type: SeoRelationshipType; targetId: string }>;
  indexable: boolean;
  status: "draft" | "published" | "retired";
};

const pageDefinitions = pageDefinitionsJson as SeoPageDefinition[];

export function getPageDefinitions() {
  return pageDefinitions;
}

export function getPageDefinition(id: string) {
  return pageDefinitions.find((definition) => definition.id === id) ?? null;
}

export function getPageDefinitionBySlug(slug: string) {
  const normalized = slug.replace(/^\//, "").replace(/\/$/, "");
  return pageDefinitions.find((definition) => definition.slug === normalized) ?? null;
}

export function isIndexable(definition: SeoPageDefinition | null) {
  return definition?.status === "published" && definition.indexable;
}

export function pageMetadata(
  definitionId: string,
  title: string,
  description: string,
  extra: Omit<Metadata, "title" | "description" | "alternates" | "robots"> = {}
): Metadata {
  const definition = getPageDefinition(definitionId);
  if (!definition) throw new Error(`Unknown SEO page definition ${definitionId}`);
  return {
    ...extra,
    title,
    description,
    alternates: { canonical: definition.canonical },
    robots: isIndexable(definition) ? { index: true, follow: true } : { index: false, follow: true }
  };
}

export function utilityPageMetadata(title: string, description: string, canonical: string): Metadata {
  return {
    title,
    description,
    alternates: { canonical },
    robots: { index: false, follow: true }
  };
}

export function reportPageMetadata(slug: string, title: string, description: string): Metadata {
  const definition = getPageDefinitionBySlug(slug);
  return {
    title,
    description,
    alternates: { canonical: `/${slug.replace(/^\//, "")}` },
    robots: isIndexable(definition) ? { index: true, follow: true } : { index: false, follow: true }
  };
}
