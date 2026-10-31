import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { TodayOutfitCard } from "@/components/body-styling/today-outfit-card";

const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock("next-intl", () => ({
  useTranslations: () => (key: string, values?: Record<string, unknown>) =>
    values ? `${key} ${JSON.stringify(values)}` : key,
}));
vi.mock("next-auth/react", () => ({
  useSession: () => ({ status: "authenticated", data: null }),
}));
vi.mock("@/lib/hooks/use-session-token", () => ({
  useSetTokenIfAvailable: () => undefined,
}));
vi.mock("@/lib/api", async (original) => ({
  ...(await original<typeof import("@/lib/api")>()),
  api: { get: mocks.get, post: mocks.post },
}));

const garment = (slot: string, kind: string, color: string) => ({
  slot,
  kind,
  color,
  color_name: "c",
  fit: "regular",
  length: "regular",
  rise: slot === "bottom" ? "mid" : null,
  material: "Cotton",
  description: `${kind} description`,
});
function today(reroll: number, available = true) {
  return {
    date: "2026-10-30",
    occasion: "work",
    style: "minimal",
    season: "autumn",
    reroll,
    weather: { temperature: 12.4, condition: "cloudy", location: "Berlin" },
    has_measurements: true,
    wardrobe_items: available ? 12 : 0,
    wardrobe_ready: available,
    outfit: {
      title: `Look ${reroll}`,
      garments: [
        garment("top", "shirt", "#ffffff"),
        garment("bottom", "trousers", "#363c41"),
        garment("shoes", "derbies", "#744f37"),
      ],
      body_reason: "reason",
      styling_tip: "tip",
      color_plan: { strategy: "contrast", accent_slots: [], echo_slots: [] },
      color_reason: "colors",
      evidence: ["height"],
    },
  };
}
function mount() {
  return render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <TodayOutfitCard />
    </QueryClientProvider>,
  );
}
beforeEach(() => {
  vi.clearAllMocks();
  mocks.get.mockImplementation(
    async (path: string, options?: { params?: Record<string, string> }) =>
      path.endsWith("/status")
        ? { enabled: true, configured: true, available: true }
        : today(Number(options?.params?.reroll || 0)),
  );
});

it("shows today's look with weather and rerolls on request", async () => {
  mount();
  expect(await screen.findByText("Look 0")).toBeTruthy();
  expect(screen.getByText(/Berlin/)).toBeTruthy();
  expect(screen.getByText("shirt description")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: /today.another/ }));
  expect(await screen.findByText("Look 1")).toBeTruthy();
  expect(mocks.get).toHaveBeenCalledWith("/body-styling/today", {
    params: { reroll: "1" },
  });
});

it("switches occasion and asks AI for an explanation of the same look", async () => {
  mocks.post.mockResolvedValue({ text: "Because it works." });
  mount();
  await screen.findByText("Look 0");
  fireEvent.click(screen.getByRole("button", { name: "occasions.formal" }));
  await waitFor(() =>
    expect(mocks.get).toHaveBeenCalledWith("/body-styling/today", {
      params: { reroll: "0", occasion: "formal" },
    }),
  );
  fireEvent.click(await screen.findByRole("button", { name: /today.explain/ }));
  expect(await screen.findByTestId("today-explanation")).toBeTruthy();
  expect(mocks.post).toHaveBeenCalledWith(
    "/body-styling/today/explain",
    undefined,
    {
      params: { reroll: "0", occasion: "formal" },
    },
  );
  expect(
    screen
      .getByRole("link", { name: /today.useWardrobe/ })
      .getAttribute("href"),
  ).toBe("/dashboard/suggest");
});
