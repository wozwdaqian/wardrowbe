import type { Garment } from "@/lib/body-styling";
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
  brands: string[];
  starter: StarterPiece[];
  sample: StyleCard | null;
};
export type StyleResult = {
  confident: boolean;
  styles: StyleDetail[];
  ranking: { id: JapaneseStyleId; name: string; tagline: string; score: number }[];
  liked_colors: string[];
  body_note: { kind: "solid" | "tall_slim"; styles: JapaneseStyleId[] } | null;
};

export function styleName(id: JapaneseStyleId, locale: string) {
  const names = JAPANESE_STYLE_NAMES[id];
  return names ? (locale.startsWith("zh") ? names.zh : names.en) : id;
}

// The quiz cards only use title and garments, so they stand in for a report outfit.
export function asOutfit(card: StyleCard) {
  return {
    title: card.title,
    garments: card.garments,
    body_reason: "",
    evidence: [],
    styling_tip: "",
  };
}
