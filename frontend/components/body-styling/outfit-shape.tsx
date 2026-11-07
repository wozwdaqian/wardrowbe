"use client";
import { useTranslations } from "next-intl";
import type { Silhouette, Technique } from "@/lib/body-styling";

// The outfit's silhouette letter and its wearing techniques, as small labelled chips.
export function OutfitShape({
  silhouette,
  techniques,
  showHint = false,
}: {
  silhouette?: Silhouette | null;
  techniques?: Technique[] | null;
  // The hover title is not reachable on touch screens, so reports spell the hint out.
  showHint?: boolean;
}) {
  const t = useTranslations("bodyStyling");
  if (!silhouette && !techniques?.length) return null;
  return (
    <div
      className="flex flex-wrap items-center gap-1.5"
      data-testid="outfit-shape"
    >
      {silhouette && (
        <span
          className="rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary"
          title={t(`silhouetteHint.${silhouette}`)}
        >
          {t(`silhouette.${silhouette}`)}
        </span>
      )}
      {techniques?.map((technique) => (
        <span
          key={technique}
          className="rounded-full border px-2 py-0.5 text-xs text-muted-foreground"
        >
          {t(`technique.${technique}`)}
        </span>
      ))}
      {showHint && silhouette && (
        <p className="w-full text-xs text-muted-foreground">
          {t(`silhouetteHint.${silhouette}`)}
        </p>
      )}
    </div>
  );
}
