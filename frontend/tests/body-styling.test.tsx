import React from "react";
import { describe, it, expect, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { OutfitIllustration } from "@/components/body-styling/outfit-illustration";
import { OutfitShape } from "@/components/body-styling/outfit-shape";
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
  it("narrows tapered hems and shows socks under ankle-length trousers", () => {
    const tapered: Garment = { ...bottom, fit: "tapered", length: "short" };
    expect(silhouetteMetrics(tapered).hemInset).toBeGreaterThan(0);
    expect(silhouetteMetrics(bottom).hemInset).toBe(0);
    const socks: Garment = {
      ...top,
      slot: "accessory",
      kind: "socks",
      color: "#fafafa",
    };
    const draw = (trousers: Garment) =>
      renderToStaticMarkup(
        <OutfitIllustration
          outfit={{ ...outfit, garments: [top, trousers, shoes, socks] }}
        />,
      );
    // Two ankle bands, one per leg, only when the hem stops above the shoe.
    expect(draw(tapered).match(/fill="#fafafa"/g)).toHaveLength(2);
    expect(draw(bottom).match(/fill="#fafafa"/g)).toHaveLength(1);
  });
  it("draws a front tuck and rolled hems only when the outfit lists them", () => {
    const plain = renderToStaticMarkup(<OutfitIllustration outfit={outfit} />);
    expect(plain).not.toContain("front-tuck");
    expect(plain).not.toContain("rolled-hem");
    const styled = renderToStaticMarkup(
      <OutfitIllustration
        outfit={{
          ...outfit,
          garments: [top, { ...bottom, kind: "chinos" }, shoes],
          techniques: ["front_tuck", "roll_hem"],
        }}
      />,
    );
    expect(styled).toContain('data-testid="front-tuck"');
    expect(styled).toContain('data-testid="rolled-hem"');
  });
  it("labels the silhouette and techniques, with the hint spelled out on request", () => {
    const markup = renderToStaticMarkup(
      <OutfitShape silhouette="H" techniques={["roll_cuffs"]} showHint />,
    );
    expect(markup).toContain("silhouette.H");
    expect(markup).toContain("technique.roll_cuffs");
    expect(markup).toContain("silhouetteHint.H");
    expect(renderToStaticMarkup(<OutfitShape />)).toBe("");
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
  it("layers a mid top over the base and draws two accessories, a tie and prints", () => {
    const markup = renderToStaticMarkup(
      <OutfitIllustration
        outfit={{
          ...outfit,
          garments: [
            { ...top, pattern: "stripe" },
            { ...top, kind: "vest", color: "#aa3322" },
            bottom,
            { ...shoes, kind: "oxfords" },
            { ...top, slot: "accessory", kind: "tie", color: "#112233" },
            { ...top, slot: "accessory", kind: "watch", color: "#445566" },
            { ...top, slot: "accessory", kind: "glasses", color: "#778899" },
          ],
        }}
      />,
    );
    // The base shirt carries a print pattern; the vest is drawn after it with its own color.
    expect(markup).toMatch(/<pattern id="fabric-[^"]*-0"/);
    expect(markup.indexOf("#aa3322")).toBeGreaterThan(
      markup.indexOf('d="M30 7 16 15'),
    );
    expect(markup).toContain('fill="#112233"');
    expect(markup).toContain("#445566");
    expect(markup).toContain("#778899");
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
