import type { Garment } from "@/lib/body-styling";

// Suggested flat (laid-flat, one side) garment measurements from body measurements and the
// garment's cut. Ranges, not sizes: brands cut differently and Japanese sizes often run small,
// so they are meant to be compared with each product's own size chart.

export type SizeKey =
  | "chest_width"
  | "length"
  | "shoulder"
  | "waist_width"
  | "hip_width"
  | "thigh_width"
  | "inseam"
  | "hem_width";
export type SizeRow = { key: SizeKey; min: number; max: number };
type Range = [number, number];
type Fit = Garment["fit"];

// Body-to-garment ease (cm, full circumference) by fit.
const TOP_EASE: Record<Fit, Range> = {
  slim: [4, 8],
  regular: [10, 16],
  relaxed: [18, 26],
  wide: [28, 36],
  tapered: [10, 16],
};
// Outerwear goes over another layer, so it needs extra room.
const OUTER_EXTRA: Range = [6, 8];
// Back length from the shoulder as a share of height.
const TOP_LENGTH: Record<Garment["length"], Range> = {
  short: [0.38, 0.4],
  regular: [0.41, 0.43],
  long: [0.45, 0.48],
};
const OUTER_LENGTH: Record<Garment["length"], Range> = {
  short: [0.38, 0.41],
  regular: [0.42, 0.46],
  long: [0.47, 0.5],
};
const COAT_LENGTH: Range = [0.55, 0.62];
// Dropped shoulders on loose cuts sit past the body's shoulder point.
const SHOULDER_EXTRA: Record<Fit, Range> = {
  slim: [-1, 1],
  regular: [-1, 1],
  relaxed: [2, 5],
  wide: [5, 9],
  tapered: [-1, 1],
};
const HIP_EASE: Record<Fit, Range> = {
  slim: [2, 6],
  regular: [6, 10],
  tapered: [10, 16],
  relaxed: [12, 18],
  wide: [18, 26],
};
const THIGH_EASE: Record<Fit, Range> = {
  slim: [2, 4],
  regular: [5, 8],
  tapered: [8, 12],
  relaxed: [10, 14],
  wide: [14, 22],
};
// Hem opening laid flat; it depends on the cut, not the body.
const HEM_WIDTH: Record<Fit, Range> = {
  slim: [15, 17],
  regular: [18, 20],
  tapered: [16, 18],
  relaxed: [20, 23],
  wide: [24, 28],
};
const INSEAM_OFFSET: Record<Garment["length"], Range> = {
  short: [-6, -3],
  regular: [-2, 1],
  long: [1, 4],
};

function measure(
  measurements: Record<string, number | string>,
  key: string,
): number | null {
  const value = measurements[key];
  return typeof value === "number" && Number.isFinite(value) && value > 0
    ? value
    : null;
}

function row(key: SizeKey, [min, max]: Range): SizeRow {
  return { key, min: Math.round(min), max: Math.round(max) };
}

const half = (base: number, [a, b]: Range): Range => [
  (base + a) / 2,
  (base + b) / 2,
];

export function garmentSizes(
  garment: Garment,
  measurements: Record<string, number | string>,
): SizeRow[] {
  const height = measure(measurements, "height");
  const chest = measure(measurements, "chest");
  const shoulder = measure(measurements, "shoulder_width");
  const rows: SizeRow[] = [];
  if (garment.slot === "top" || garment.slot === "outerwear") {
    const outer = garment.slot === "outerwear";
    const [a, b] = TOP_EASE[garment.fit];
    const ease: Range = outer
      ? [a + OUTER_EXTRA[0], b + OUTER_EXTRA[1]]
      : [a, b];
    if (chest) rows.push(row("chest_width", half(chest, ease)));
    if (shoulder && garment.kind !== "vest") {
      const [lo, hi] = SHOULDER_EXTRA[garment.fit];
      rows.push(row("shoulder", [shoulder + lo, shoulder + hi]));
    }
    if (height) {
      const share = ["coat", "trench"].includes(garment.kind)
        ? COAT_LENGTH
        : (outer ? OUTER_LENGTH : TOP_LENGTH)[garment.length];
      rows.push(row("length", [height * share[0], height * share[1]]));
    }
  }
  if (garment.slot === "bottom") {
    const waist = measure(measurements, "waist");
    const hips = measure(measurements, "hips");
    const thigh = measure(measurements, "thigh");
    const inseam = measure(measurements, "inseam");
    if (waist) rows.push(row("waist_width", [waist / 2, (waist + 2) / 2]));
    if (hips) rows.push(row("hip_width", half(hips, HIP_EASE[garment.fit])));
    if (thigh)
      rows.push(row("thigh_width", half(thigh, THIGH_EASE[garment.fit])));
    if (garment.kind !== "shorts") {
      if (inseam) {
        const [lo, hi] = INSEAM_OFFSET[garment.length];
        rows.push(row("inseam", [inseam + lo, inseam + hi]));
      }
      rows.push(row("hem_width", HEM_WIDTH[garment.fit]));
    }
  }
  return rows;
}

// Which optional measurement would add a row, so the page can say what to fill in.
export function missingForSizes(
  garment: Garment,
  measurements: Record<string, number | string>,
): ("inseam" | "shoulder_width")[] {
  const missing: ("inseam" | "shoulder_width")[] = [];
  if (
    garment.slot === "bottom" &&
    garment.kind !== "shorts" &&
    !measure(measurements, "inseam")
  )
    missing.push("inseam");
  if (
    (garment.slot === "top" || garment.slot === "outerwear") &&
    garment.kind !== "vest" &&
    !measure(measurements, "shoulder_width")
  )
    missing.push("shoulder_width");
  return missing;
}
