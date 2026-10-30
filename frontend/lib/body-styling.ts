import catalog from "@/lib/generated/body-styling-catalog.json";
export { catalog as STYLING_CATALOG };
export type ColorFamily = keyof typeof catalog.color_families;
export type MaterialCode = keyof typeof catalog.materials;
export type StylingProfile = {
  skin_depth?: keyof typeof catalog.skin_depth | null;
  undertone?: keyof typeof catalog.undertone | null;
  hair_color?: keyof typeof catalog.hair_color | null;
  eye_color?: keyof typeof catalog.eye_color | null;
  contrast_preference?: keyof typeof catalog.contrast_preference | null;
  preferred_color_families?: ColorFamily[];
  avoided_color_families?: ColorFamily[];
  avoided_materials?: MaterialCode[];
  fabric_preferences?: (keyof typeof catalog.fabric_preferences)[];
  fit_issues?: (keyof typeof catalog.fit_issues)[];
};
export const PROFILE_CATALOGS = {
  skin_depth: "skin_depth",
  undertone: "undertone",
  hair_color: "hair_color",
  eye_color: "eye_color",
  contrast_preference: "contrast_preference",
  preferred_color_families: "color_families",
  avoided_color_families: "color_families",
  avoided_materials: "materials",
  fabric_preferences: "fabric_preferences",
  fit_issues: "fit_issues",
} as const;
export function catalogLabel(
  group: keyof typeof catalog,
  value: string,
  locale: string,
) {
  const entries = catalog[group] as Record<string, { zh: string; en: string }>;
  return entries[value]?.[locale.startsWith("zh") ? "zh" : "en"] || value;
}
export type FabricSpec = {
  [K in
    | "construction"
    | "weight"
    | "drape"
    | "sheen"
    | "stretch"]: keyof (typeof catalog)[K];
};
export type StyleExplanation = { text: string; evidence: FactId[] };
export type ColorPlan = {
  strategy: keyof typeof catalog.color_strategy;
  accent_slots: Garment["slot"][];
  echo_slots: Garment["slot"][];
};
export type OutfitFeedback = {
  outfit_index: number;
  overall?: "like" | "dislike" | null;
  colors?: "like" | "dislike" | null;
  fabrics?: "like" | "dislike" | null;
};
export type ReportFeedback = { outfits: OutfitFeedback[] };

export type Goal =
  | "balance"
  | "elongate_legs"
  | "midsection"
  | "shoulders"
  | "comfort";
export type Context = {
  occasion: "daily" | "work" | "date" | "weekend" | "formal";
  style: "minimal" | "smart_casual" | "street" | "sporty" | "classic";
  goals: Goal[];
  season: "all" | "spring" | "summer" | "autumn" | "winter";
};
export const DEFAULT_CONTEXT: Context = {
  occasion: "daily",
  style: "minimal",
  goals: ["balance", "comfort"],
  season: "all",
};
export const MEASUREMENT_FIELDS = [
  "height",
  "chest",
  "waist",
  "hips",
  "weight",
  "inseam",
  "shoulder_width",
  "thigh",
] as const;
export type MeasurementKey = (typeof MEASUREMENT_FIELDS)[number];
export type FactId =
  | MeasurementKey
  | "shoulder_type"
  | "waist_chest_ratio"
  | "waist_hips_ratio"
  | "inseam_height_ratio"
  | PersonalFactId;
export type PersonalFactId = keyof StylingProfile | "previous_feedback";
export type Fact = {
  id: FactId;
  value: number | string | string[];
  unit: "cm" | "kg" | "ratio" | "self_report";
};
export type Garment = {
  slot: "top" | "bottom" | "shoes" | "outerwear" | "accessory";
  kind:
    | "tshirt"
    | "polo"
    | "shirt"
    | "knit"
    | "sweatshirt"
    | "trousers"
    | "jeans"
    | "shorts"
    | "sneakers"
    | "loafers"
    | "boots"
    | "derbies"
    | "blazer"
    | "jacket"
    | "coat"
    | "scarf"
    | "belt"
    | "bag"
    | "cap";
  color: string;
  color_name: string;
  fit: "slim" | "regular" | "relaxed" | "wide";
  length: "short" | "regular" | "long";
  rise: "low" | "mid" | "high" | null;
  material: string;
  description: string;
  material_code?: MaterialCode | null;
  color_family?: ColorFamily | null;
  fabric?: FabricSpec | null;
  fabric_summary?: string | null;
  fabric_reason?: string | null;
};
export type BodyOutfit = {
  title: string;
  garments: Garment[];
  body_reason: string;
  evidence: FactId[];
  styling_tip: string;
  color_plan?: ColorPlan | null;
  color_reason?: StyleExplanation | null;
  fabric_reason?: StyleExplanation | null;
};
export type Observation = { text: string; evidence: FactId[] };
export type FitAdvice = Observation & {
  area: "top_length" | "trouser_rise" | "trouser_leg" | "outerwear";
};
export type BodyStyleReport = {
  id: string;
  created_at: string;
  model: string;
  input_snapshot: {
    measurements: Record<string, number | string>;
    context: Context;
    styling_profile?: StylingProfile;
    contract_version?: number;
  };
  facts: Fact[];
  result: {
    summary: string;
    observations: Observation[];
    fit_advice: FitAdvice[];
    unknowns: string[];
    outfits: BodyOutfit[];
    color_guidance?: StyleExplanation | null;
    fabric_guidance?: StyleExplanation | null;
  };
  feedback?: ReportFeedback | null;
};
export type HistoryEntry = {
  id: string;
  created_at: string;
  summary: string;
  context: Context;
};
export type BodyStyleHistory = {
  items: HistoryEntry[];
  total: number;
  offset: number;
  limit: number;
};
export type AIStatus = {
  enabled: boolean;
  configured: boolean;
  available: boolean;
};

// The same validated visual attributes shown in the text determine the drawing.
export function silhouetteMetrics(garment: Garment) {
  const width = { slim: 72, regular: 86, relaxed: 101, wide: 116 }[garment.fit];
  const topHeight = { short: 93, regular: 112, long: 136 }[garment.length];
  const bottomY = { high: 136, mid: 149, low: 161 }[garment.rise || "mid"];
  const legHeight =
    garment.kind === "shorts"
      ? 88
      : { short: 157, regular: 177, long: 192 }[garment.length];
  return { width, topHeight, bottomY, legHeight };
}
