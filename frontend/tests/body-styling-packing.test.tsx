import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import PackingPage from "@/app/dashboard/body-styling/packing/page";
import { ApiError } from "@/lib/api";

const mocks = vi.hoisted(() => ({ post: vi.fn() }));
vi.mock("next-intl", () => ({
  useLocale: () => "en",
  useTranslations: () => (key: string, values?: Record<string, unknown>) =>
    values ? `${key} ${JSON.stringify(values)}` : key,
}));
vi.mock("@/lib/api", async (original) => ({
  ...(await original<typeof import("@/lib/api")>()),
  api: { post: mocks.post },
}));

function mount() {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <PackingPage />
    </QueryClientProvider>,
  );
}
const piece = (index: number, description: string, owned = false) => ({
  index,
  slot: "top",
  kind: "shirt",
  color: "#ffffff",
  description,
  days: ["2026-12-01"],
  owned: owned ? { id: "i1", name: "My shirt", same_color: true } : null,
});
beforeEach(() => vi.clearAllMocks());

it("sends the trip and shows a checkable list with daily outfits", async () => {
  mocks.post.mockResolvedValue({
    location: "Oslo",
    forecast_days: 2,
    pieces: [piece(0, "White shirt", true), piece(1, "Grey trousers")],
    days: [
      {
        date: "2026-12-01",
        occasion: "formal",
        season: "winter",
        temp_min: -2,
        temp_max: 3,
        pieces: [0, 1],
      },
    ],
  });
  mount();
  fireEvent.change(screen.getByPlaceholderText("packing.cityPlaceholder"), {
    target: { value: "Oslo" },
  });
  fireEvent.click(screen.getByRole("button", { name: "occasions.formal" }));
  fireEvent.click(screen.getByRole("button", { name: "packing.submit" }));
  await screen.findByTestId("packing-result");
  expect(mocks.post.mock.calls[0][1]).toMatchObject({
    city: "Oslo",
    occasions: ["work", "formal"],
    style: "minimal",
  });
  expect(screen.getByText(/packing.owned/)).toBeTruthy();
  expect(screen.getByText(/packing.toBuy/)).toBeTruthy();
  expect(screen.getByText("White shirt / Grey trousers")).toBeTruthy();
  const box = screen.getAllByRole("checkbox")[0];
  fireEvent.click(box);
  await waitFor(() => expect(box.getAttribute("data-state")).toBe("checked"));
});

it("explains an unknown city", async () => {
  mocks.post.mockRejectedValue(
    new ApiError("bad", 422, { detail: { code: "unknown_city" } }),
  );
  mount();
  fireEvent.click(screen.getByRole("button", { name: "packing.submit" }));
  expect(await screen.findByText("packing.unknownCity")).toBeTruthy();
});
