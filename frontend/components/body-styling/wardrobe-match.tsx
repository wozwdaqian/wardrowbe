"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { ShoppingBag } from "lucide-react";
import { cn } from "@/lib/utils";

export type WardrobeGarmentMatch = {
  slot: string;
  kind: string;
  status: "owned" | "similar" | "missing";
  matches: { id: string; name: string | null; thumbnail_url: string | null }[];
};
export type WardrobeMatch = {
  wardrobe_items: number;
  combinations: number;
  outfits: { garments: WardrobeGarmentMatch[] }[];
  suggestions: {
    outfit_index: number;
    garment_index: number;
    description: string;
    gain: number;
  }[];
};

export function GarmentWardrobeStatus({
  match,
}: {
  match: WardrobeGarmentMatch | undefined;
}) {
  const t = useTranslations("bodyStyling");
  if (!match) return null;
  return (
    <div
      className="mt-2 flex flex-wrap items-center gap-2"
      data-testid="garment-wardrobe"
    >
      <span
        className={cn(
          "rounded-full px-2 py-0.5 text-[11px]",
          match.status === "owned"
            ? "bg-emerald-100 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-200"
            : match.status === "similar"
              ? "bg-sky-100 text-sky-900 dark:bg-sky-950 dark:text-sky-200"
              : "bg-muted text-muted-foreground",
        )}
      >
        {t("wardrobe." + match.status)}
      </span>
      {match.matches.map((item) =>
        item.thumbnail_url ? (
          <Link key={item.id} href={`/dashboard/wardrobe?item=${item.id}`}>
            {/* eslint-disable-next-line @next/next/no-img-element -- signed, already-sized thumbnail */}
            <img
              src={item.thumbnail_url}
              alt={item.name || t("wardrobe.itemFallback")}
              className="h-9 w-9 rounded-md border object-cover"
            />
          </Link>
        ) : null,
      )}
    </div>
  );
}

export function WardrobeSuggestions({ match }: { match: WardrobeMatch }) {
  const t = useTranslations("bodyStyling");
  if (!match.wardrobe_items) {
    return (
      <p className="text-sm text-muted-foreground">
        {t("wardrobe.empty")}{" "}
        <Link href="/dashboard/wardrobe" className="underline">
          {t("wardrobe.upload")}
        </Link>
      </p>
    );
  }
  if (!match.suggestions.length) {
    return <p className="text-sm">{t("wardrobe.complete")}</p>;
  }
  return (
    <div className="space-y-2" data-testid="wardrobe-suggestions">
      <p className="flex items-center gap-2 text-sm font-semibold">
        <ShoppingBag className="h-4 w-4" />
        {t("wardrobe.suggestTitle", { combinations: match.combinations })}
      </p>
      <ul className="space-y-1.5 text-sm">
        {match.suggestions.map((s) => (
          <li key={`${s.outfit_index}-${s.garment_index}`}>
            {s.description}{" "}
            <span className="text-muted-foreground">
              {s.gain > 0
                ? t("wardrobe.gain", { count: s.gain })
                : t("wardrobe.noGain")}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
