import React from "react";
import { describe, it, expect, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { OutfitIllustration } from "@/components/body-styling/outfit-illustration";
import {
  Garment,
  BodyOutfit,
  silhouetteMetrics,
  DEFAULT_CONTEXT,
} from "@/lib/body-styling";
vi.mock("next-intl", () => ({ useTranslations: () => (key: string) => key }));
const top: Garment = {
  slot: "top",
  kind: "shirt",
  color: "#345678",
  color_name: "Blue",
  fit: "regular",
  length: "regular",
  rise: null,
  material: "Cotton",
  description: "Hip length shirt",
};
const bottom: Garment = {
  ...top,
  slot: "bottom",
  kind: "trousers",
  rise: "high",
};
const shoes: Garment = { ...top, slot: "shoes", kind: "sneakers" };
const outfit: BodyOutfit = {
  title: "Look <script>alert(1)</script>",
  garments: [top, bottom, shoes],
  body_reason: "Test",
  evidence: ["height"],
  styling_tip: "Test",
};
describe("body styling illustrations", () => {
  it("draws the supplied palette without accepting SVG or HTML from the model", () => {
    const markup = renderToStaticMarkup(<OutfitIllustration outfit={outfit} />);
    expect(markup).toContain('fill="#345678"');
    expect(markup).toContain('role="img"');
    expect(markup).not.toContain("<script>");
    expect(markup).not.toContain("<image");
  });
  it("changes silhouette width and hem with the same attributes displayed in text", () => {
    const regular = silhouetteMetrics(top),
      wide = silhouetteMetrics({ ...top, fit: "wide", length: "long" });
    expect(wide.width).toBeGreaterThan(regular.width);
    expect(wide.topHeight).toBeGreaterThan(regular.topHeight);
    expect(silhouetteMetrics({ ...bottom, rise: "high" }).bottomY).toBeLessThan(
      silhouetteMetrics({ ...bottom, rise: "low" }).bottomY,
    );
    expect(
      silhouetteMetrics({ ...bottom, length: "short" }).legHeight,
    ).toBeLessThan(silhouetteMetrics(bottom).legHeight);
  });
  it("renders optional outerwear and accessories without remote assets", () => {
    const markup = renderToStaticMarkup(
      <OutfitIllustration
        outfit={{
          ...outfit,
          garments: [
            top,
            bottom,
            shoes,
            { ...top, slot: "outerwear", kind: "coat" },
            { ...top, slot: "accessory", kind: "bag" },
          ],
        }}
      />,
    );
    expect(markup).toContain("<svg");
    expect(markup).not.toContain("https:");
  });
  it("starts with the agreed context", () => {
    expect(DEFAULT_CONTEXT).toEqual({
      occasion: "daily",
      style: "minimal",
      goals: ["balance", "comfort"],
      season: "all",
    });
  });
});
