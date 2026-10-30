import React, { useState } from "react";
import fs from "node:fs";
import path from "node:path";
import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { StylingProfileEditor } from "@/components/body-styling/styling-profile-editor";
import { OutfitIllustration } from "@/components/body-styling/outfit-illustration";
import {
  BodyOutfit,
  StylingProfile,
  STYLING_CATALOG,
} from "@/lib/body-styling";
vi.mock("next-intl", () => ({
  useLocale: () => "zh-CN",
  useTranslations: () => (key: string) => key,
}));

it("keeps the server and browser color/fabric vocabularies identical", () => {
  const source = JSON.parse(
    fs.readFileSync(
      path.resolve(
        process.cwd(),
        "../backend/app/data/body_styling_catalog.json",
      ),
      "utf8",
    ),
  );
  expect(STYLING_CATALOG).toEqual(source);
});
it("moves a color family between preferences without saving contradictory values", () => {
  function Editor() {
    const [value, setValue] = useState<StylingProfile>({});
    return <StylingProfileEditor value={value} onChange={setValue} />;
  }
  render(<Editor />);
  fireEvent.click(screen.getByTestId("preferred_color_families-green"));
  expect(screen.getByTestId("preferred_color_families-green")).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  fireEvent.click(screen.getByTestId("avoided_color_families-green"));
  expect(screen.getByTestId("preferred_color_families-green")).toHaveAttribute(
    "aria-pressed",
    "false",
  );
  expect(screen.getByTestId("avoided_color_families-green")).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  expect(
    (screen.getByLabelText("personal.undertone") as HTMLSelectElement).value,
  ).toBe("");
});
it("renders local fabric patterns from structured construction and keeps colors", () => {
  const piece = {
    slot: "top",
    kind: "shirt",
    color: "#718575",
    color_name: "Sage",
    fit: "regular",
    length: "short",
    rise: null,
    material: "Cotton",
    description: "Test",
    fabric: {
      construction: "twill",
      weight: "medium",
      drape: "crisp",
      sheen: "matte",
      stretch: "none",
    },
  } as const;
  const outfit: BodyOutfit = {
    title: "Test",
    garments: [
      piece,
      { ...piece, slot: "bottom", kind: "trousers", rise: "mid" },
      { ...piece, slot: "shoes", kind: "sneakers", fabric: null },
    ],
    body_reason: "Test",
    evidence: ["height"],
    styling_tip: "Test",
  };
  const output = renderToStaticMarkup(<OutfitIllustration outfit={outfit} />);
  expect(output).toContain("<pattern");
  expect(output).toContain('fill="#718575"');
  expect(output).toContain("url(#fabric-");
  expect(output).not.toContain("<image");
  expect(output).not.toContain("<script");
});
