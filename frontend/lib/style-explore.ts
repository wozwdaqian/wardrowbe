import type { Garment, Silhouette, Technique } from "@/lib/body-styling";
import {
  JAPANESE_STYLE_NAMES,
  type JapaneseStyleId,
} from "@/lib/generated/japanese-styles";

export type Answer = "like" | "neutral" | "dislike";
export type StyleCard = {
  id: string;
  title: string;
  tags: string[];
  garments: Garment[];
  techniques?: Technique[];
  silhouette?: Silhouette | null;
};
export type StarterPiece = {
  description: string;
  kind: string;
  color: string;
  status: "owned" | "similar" | "missing";
  matches: { id: string; name: string | null }[];
};
export type StyleDetail = {
  id: JapaneseStyleId;
  base_style: string;
  name: string;
  name_ja: string;
  tagline: string;
  description: string;
  keywords: string[];
  tips: string[];
  pitfalls: string[];
  search: { zh: string[]; ja: string[] };
  // Ordered with the user's budget tier first.
  brands: { name: string; tier: BrandTier }[];
  starter: StarterPiece[];
  sample: StyleCard | null;
};
export type BrandTier = "budget" | "mid" | "premium";
export type DressCode = "suit" | "business_casual" | "smart_casual" | "casual";
export const DRESS_CODES: DressCode[] = [
  "suit",
  "business_casual",
  "smart_casual",
  "casual",
];
export const BRAND_TIERS: BrandTier[] = ["budget", "mid", "premium"];
export type Lifestyle = { dress_code?: DressCode; budget?: BrandTier };
export type StylePlan = {
  weekday: { id: JapaneseStyleId; name: string };
  weekend: { id: JapaneseStyleId; name: string };
  switches: boolean;
};
export type StyleResult = {
  confident: boolean;
  // Weekday and weekend styles, once work's dress code is known.
  plan: StylePlan | null;
  styles: StyleDetail[];
  ranking: {
    id: JapaneseStyleId;
    name: string;
    tagline: string;
    score: number;
  }[];
  liked_colors: string[];
  body_note: { kind: "solid" | "tall_slim"; styles: JapaneseStyleId[] } | null;
};

// Consecutive brands of one tier, keeping the server's order (the user's tier first).
export function brandGroups(brands: StyleDetail["brands"]) {
  const groups: { tier: BrandTier; names: string[] }[] = [];
  for (const brand of brands) {
    const last = groups[groups.length - 1];
    if (last && last.tier === brand.tier) last.names.push(brand.name);
    else groups.push({ tier: brand.tier, names: [brand.name] });
  }
  return groups;
}

export function styleName(id: JapaneseStyleId, locale: string) {
  const names = JAPANESE_STYLE_NAMES[id];
  return names ? (locale.startsWith("zh") ? names.zh : names.en) : id;
}

// The quiz cards only use title and garments, so they stand in for a report outfit.
export function asOutfit(card: StyleCard) {
  return {
    title: card.title,
    garments: card.garments,
    techniques: card.techniques,
    silhouette: card.silhouette,
    body_reason: "",
    evidence: [],
    styling_tip: "",
  };
}
