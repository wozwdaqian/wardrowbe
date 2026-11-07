import { describe, expect, it } from "vitest";
import type { Garment } from "@/lib/body-styling";
import { garmentSizes, missingForSizes } from "@/lib/size-guide";
import { brandGroups } from "@/lib/style-explore";

const base: Garment = {
  slot: "top",
  kind: "tshirt",
  color: "#ffffff",
  color_name: "White",
  fit: "regular",
  length: "regular",
  rise: null,
  material: "Cotton",
  description: "",
};
const body = { height: 172, chest: 96, waist: 84, hips: 95 };
const get = (rows: ReturnType<typeof garmentSizes>, key: string) =>
  rows.find((r) => r.key === key);

describe("suggested flat measurements", () => {
  it("adds chest ease by fit and length by height", () => {
    const regular = garmentSizes(base, body);
    expect(get(regular, "chest_width")).toEqual({
      key: "chest_width",
      min: 53,
      max: 56,
    });
    expect(get(regular, "length")).toEqual({ key: "length", min: 71, max: 74 });
    const relaxed = garmentSizes({ ...base, fit: "relaxed" }, body);
    expect(get(relaxed, "chest_width")!.min).toBeGreaterThan(
      get(regular, "chest_width")!.max,
    );
  });
  it("gives outerwear room for a layer and coats a longer length", () => {
    const jacket = garmentSizes(
      { ...base, slot: "outerwear", kind: "jacket" },
      body,
    );
    expect(get(jacket, "chest_width")!.min).toBeGreaterThan(
      get(garmentSizes(base, body), "chest_width")!.min,
    );
    const coat = garmentSizes(
      { ...base, slot: "outerwear", kind: "coat" },
      body,
    );
    expect(get(coat, "length")!.min).toBeGreaterThan(90);
  });
  it("sizes trousers from waist, hips and optional inseam", () => {
    const chinos: Garment = {
      ...base,
      slot: "bottom",
      kind: "chinos",
      rise: "mid",
    };
    const rows = garmentSizes(chinos, body);
    expect(get(rows, "waist_width")).toEqual({
      key: "waist_width",
      min: 42,
      max: 43,
    });
    expect(get(rows, "inseam")).toBeUndefined();
    expect(missingForSizes(chinos, body)).toEqual(["inseam"]);
    const withInseam = { ...body, inseam: 78 };
    const ankle = get(
      garmentSizes({ ...chinos, length: "short" }, withInseam),
      "inseam",
    )!;
    const full = get(garmentSizes(chinos, withInseam), "inseam")!;
    expect(ankle.max).toBeLessThan(full.min + 1);
    expect(
      get(garmentSizes({ ...chinos, fit: "tapered" }, body), "hem_width")!.max,
    ).toBeLessThan(
      get(garmentSizes({ ...chinos, fit: "wide" }, body), "hem_width")!.min,
    );
  });
  it("adds dropped shoulders for loose cuts and skips shoes", () => {
    const withShoulder = { ...body, shoulder_width: 44 };
    expect(get(garmentSizes(base, withShoulder), "shoulder")).toEqual({
      key: "shoulder",
      min: 43,
      max: 45,
    });
    expect(
      get(garmentSizes({ ...base, fit: "wide" }, withShoulder), "shoulder")!
        .min,
    ).toBe(49);
    expect(
      garmentSizes({ ...base, slot: "shoes", kind: "sneakers" }, body),
    ).toEqual([]);
    expect(garmentSizes(base, { height: "x" as unknown as number })).toEqual(
      [],
    );
  });
});

describe("brand groups", () => {
  it("groups consecutive tiers in the server's order", () => {
    expect(
      brandGroups([
        { name: "A", tier: "budget" },
        { name: "B", tier: "budget" },
        { name: "C", tier: "mid" },
      ]),
    ).toEqual([
      { tier: "budget", names: ["A", "B"] },
      { tier: "mid", names: ["C"] },
    ]);
  });
});
