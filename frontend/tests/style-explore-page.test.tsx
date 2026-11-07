import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import StyleExplorePage from "@/app/dashboard/body-styling/style/page";

const mocks = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  profile: { styling_profile: {} } as Record<string, unknown>,
  openAssistant: vi.fn(),
}));
vi.mock("next-intl", () => ({
  useLocale: () => "zh-CN",
  useTranslations: () => (key: string, values?: Record<string, unknown>) =>
    values ? `${key} ${JSON.stringify(values)}` : key,
}));
vi.mock("@/lib/api", async (original) => ({
  ...(await original<typeof import("@/lib/api")>()),
  api: { get: mocks.get, post: mocks.post, patch: mocks.patch },
}));
vi.mock("@/lib/hooks/use-user", () => ({
  useUserProfile: () => ({ data: mocks.profile }),
}));
vi.mock("@/components/assistant/assistant-panel", () => ({
  openAssistant: mocks.openAssistant,
}));

const garment = (slot: string, kind: string, description: string) => ({
  slot,
  kind,
  color: "#243b55",
  color_name: "藏蓝色",
  fit: "regular",
  length: "regular",
  rise: slot === "bottom" ? "mid" : null,
  pattern: "solid",
  material_code: "cotton",
  description,
});
const card = (id: string, title: string) => ({
  id,
  title,
  tags: ["宽松叠穿"],
  garments: [
    garment("top", "shirt", `${title} 上衣`),
    garment("bottom", "chinos", `${title} 裤子`),
    garment("shoes", "sneakers", `${title} 鞋`),
  ],
});
const detail = {
  id: "cityboy",
  base_style: "street",
  name: "Cityboy 城市男孩",
  name_ja: "シティボーイ",
  tagline: "宽松叠穿、大地色、不刻意",
  description: "源自日本杂志《POPEYE》。",
  keywords: ["宽松", "叠穿"],
  tips: ["先从一件宽松衬衫开始"],
  pitfalls: ["整身都大一号会显得邋遢"],
  search: { zh: ["cityboy 穿搭"], ja: ["シティボーイ コーデ メンズ"] },
  brands: [
    { name: "UNIQLO U", tier: "budget" },
    { name: "BEAMS", tier: "mid" },
  ],
  starter: [
    {
      description: "浅蓝色宽松衬衫",
      kind: "shirt",
      color: "#b5ccd4",
      status: "owned",
      matches: [{ id: "i1", name: "我的浅蓝衬衫" }],
    },
    { description: "藏蓝色阔腿卡其裤", kind: "chinos", color: "#243b55", status: "missing", matches: [] },
  ],
  sample: card("cityboy:0", "衬衫当外套"),
};

function mount() {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <StyleExplorePage />
    </QueryClientProvider>,
  );
}
beforeEach(() => {
  vi.clearAllMocks();
  mocks.profile = { styling_profile: {} };
});

it("runs both rounds, shows the result and saves the style", async () => {
  mocks.get.mockResolvedValue({
    cards: [card("cityboy:0", "衬衫当外套"), card("mode:0", "全黑宽松")],
  });
  mocks.post.mockImplementation(async (path: string) =>
    path.endsWith("round-two")
      ? { cards: [card("cityboy:1", "条纹 T 恤")] }
      : {
          confident: true,
          styles: [detail],
          ranking: [
            { id: "cityboy", name: "Cityboy 城市男孩", tagline: "x", score: 100 },
            { id: "mode", name: "暗黑 Mode", tagline: "y", score: 0 },
          ],
          liked_colors: ["蓝色系"],
          body_note: { kind: "solid", styles: ["workwear"] },
        },
  );
  mocks.patch.mockResolvedValue({ preferred_styles: ["cityboy"] });
  Object.assign(navigator, { clipboard: { writeText: vi.fn().mockResolvedValue(undefined) } });
  mount();
  fireEvent.click(screen.getByRole("button", { name: "start" }));
  expect(await screen.findByText("衬衫当外套")).toBeTruthy();
  expect(screen.getByText('progress {"current":1,"total":2}')).toBeTruthy();
  expect(screen.getByTestId("outfit-illustration")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "like" }));
  expect(await screen.findByText("全黑宽松")).toBeTruthy();
  // Going back lets the user change an answer.
  fireEvent.click(screen.getByRole("button", { name: "previous" }));
  expect(screen.getByText("衬衫当外套")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "like" }));
  fireEvent.click(screen.getByRole("button", { name: "dislike" }));
  expect(await screen.findByText("条纹 T 恤")).toBeTruthy();
  expect(mocks.post).toHaveBeenCalledWith("/body-styling/style-explore/round-two", {
    answers: { "cityboy:0": "like", "mode:0": "dislike" },
  });
  fireEvent.click(screen.getByRole("button", { name: "like" }));
  await screen.findByTestId("style-result");
  expect(mocks.post).toHaveBeenLastCalledWith("/body-styling/style-explore/result", {
    answers: { "cityboy:0": "like", "mode:0": "dislike", "cityboy:1": "like" },
  });
  expect(screen.getAllByTestId("ranking-row")).toHaveLength(2);
  expect(screen.getByText("bodyNote.solid")).toBeTruthy();
  const pieces = screen.getAllByTestId("starter-piece");
  expect(pieces[0].textContent).toContain("我的浅蓝衬衫");
  expect(pieces[0].textContent).toContain("status.owned");
  expect(pieces[1].textContent).toContain("status.missing");

  fireEvent.click(screen.getByRole("button", { name: 'copy {"term":"cityboy 穿搭"}' }));
  await waitFor(() =>
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith("cityboy 穿搭"),
  );
  fireEvent.click(screen.getByRole("button", { name: /ask/ }));
  expect(mocks.openAssistant).toHaveBeenCalledWith(
    'askPrompt {"style":"Cityboy 城市男孩"}',
  );
  fireEvent.click(screen.getByRole("button", { name: "save" }));
  expect(await screen.findByText("saved")).toBeTruthy();
  expect(mocks.patch).toHaveBeenCalledWith("/body-styling/style-explore/styles", {
    styles: ["cityboy"],
  });
});

it("shows the saved style and offers a retake", async () => {
  mocks.profile = { styling_profile: { preferred_styles: ["ivy", "kireime"] } };
  mount();
  expect(screen.getByTestId("current-styles").textContent).toContain(
    "日式常春藤 · 学院 · きれいめ 清爽干净",
  );
  expect(screen.getByRole("button", { name: "retake" })).toBeTruthy();
});

it("skips straight to the result when round two has nothing new", async () => {
  mocks.get.mockResolvedValue({ cards: [card("mode:0", "全黑宽松")] });
  mocks.post.mockImplementation(async (path: string) =>
    path.endsWith("round-two")
      ? { cards: [] }
      : { confident: false, styles: [detail], ranking: [], liked_colors: [], body_note: null },
  );
  mount();
  fireEvent.click(screen.getByRole("button", { name: "start" }));
  await screen.findByText("全黑宽松");
  fireEvent.click(screen.getByRole("button", { name: "dislike" }));
  await screen.findByTestId("style-result");
  expect(screen.getByText("unsure")).toBeTruthy();
});

it("plans weekdays from the dress code and keeps it when saving", async () => {
  mocks.profile = { styling_profile: { budget: "mid" } };
  mocks.get.mockResolvedValue({ cards: [card("cityboy:0", "衬衫当外套")] });
  const result = (plan: unknown) => ({
    confident: true,
    plan,
    styles: [detail],
    ranking: [
      { id: "cityboy", name: "Cityboy 城市男孩", tagline: "x", score: 100 },
    ],
    liked_colors: [],
    body_note: null,
  });
  mocks.post.mockImplementation(
    async (path: string, body: { dress_code?: string }) =>
      path.endsWith("round-two")
        ? { cards: [] }
        : result(
            body.dress_code === "suit"
              ? {
                  weekday: { id: "kireime", name: "きれいめ 清爽干净" },
                  weekend: { id: "cityboy", name: "Cityboy 城市男孩" },
                  switches: true,
                }
              : null,
          ),
  );
  mocks.patch.mockResolvedValue({ preferred_styles: ["cityboy"] });
  mount();
  fireEvent.click(screen.getByRole("button", { name: "start" }));
  await screen.findByText("衬衫当外套");
  fireEvent.click(screen.getByRole("button", { name: "like" }));
  await screen.findByTestId("style-lifestyle");
  // The saved budget is sent from the start; brands show their tiers.
  expect(mocks.post).toHaveBeenLastCalledWith(
    "/body-styling/style-explore/result",
    {
      answers: { "cityboy:0": "like" },
      budget: "mid",
    },
  );
  // One budget button plus the brand tier heading.
  expect(screen.getAllByText("tiers.budget")).toHaveLength(2);
  fireEvent.click(
    screen.getByRole("button", { name: "lifestyle.dressCodes.suit" }),
  );
  expect((await screen.findByTestId("style-plan")).textContent).toContain(
    "planSwitch",
  );
  expect(mocks.post).toHaveBeenLastCalledWith(
    "/body-styling/style-explore/result",
    {
      answers: { "cityboy:0": "like" },
      budget: "mid",
      dress_code: "suit",
    },
  );
  fireEvent.click(screen.getByRole("button", { name: "save" }));
  await screen.findByText("saved");
  expect(mocks.patch).toHaveBeenCalledWith(
    "/body-styling/style-explore/styles",
    {
      styles: ["cityboy"],
      budget: "mid",
      dress_code: "suit",
    },
  );
});
