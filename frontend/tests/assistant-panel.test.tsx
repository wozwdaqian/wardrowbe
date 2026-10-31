import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { AssistantPanel, openAssistant } from "@/components/assistant/assistant-panel";

const mocks = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  stream: vi.fn(),
  upload: vi.fn(),
}));
vi.mock("next-intl", () => ({
  useTranslations: () => (key: string, values?: Record<string, unknown>) =>
    values ? `${key} ${JSON.stringify(values)}` : key,
}));
vi.mock("@/lib/api", async (original) => ({
  ...(await original<typeof import("@/lib/api")>()),
  api: { get: mocks.get, post: mocks.post },
  streamApi: mocks.stream,
  uploadApi: mocks.upload,
}));

async function* events(...items: Record<string, unknown>[]) {
  for (const item of items) yield item;
}
const pending = {
  id: "a1",
  tool: "update_profile",
  status: "pending",
  summary: "腰围 90 → 88",
  result: null,
  undoable: false,
};
let client: QueryClient;
function mount() {
  client = new QueryClient();
  vi.spyOn(client, "invalidateQueries");
  return render(
    <QueryClientProvider client={client}>
      <AssistantPanel />
    </QueryClientProvider>,
  );
}
beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  URL.createObjectURL = vi.fn((file: Blob) => `blob:${(file as File).name}`);
  URL.revokeObjectURL = vi.fn();
});

function photo(name: string) {
  return new File(["x"], name, { type: "image/jpeg" });
}

it("creates a conversation, streams the reply and confirms a proposal", async () => {
  mocks.post.mockImplementation(async (path: string) =>
    path === "/assistant/conversations"
      ? { id: "c1" }
      : { ...pending, status: "applied", undoable: true },
  );
  mocks.stream
    .mockReturnValueOnce(
      events(
        { type: "tool", name: "update_profile" },
        { type: "action", action: pending },
        { type: "message", id: "m1", content: "请确认。" },
        { type: "done" },
      ),
    )
    .mockReturnValueOnce(events({ type: "message", id: "m2", content: "已更新。" }));
  mount();
  fireEvent.click(screen.getByRole("button", { name: "open" }));
  fireEvent.change(screen.getByLabelText("placeholder"), {
    target: { value: "我腰围 88" },
  });
  fireEvent.click(screen.getByRole("button", { name: "send" }));
  expect(await screen.findByText("请确认。")).toBeTruthy();
  expect(mocks.stream).toHaveBeenCalledWith("/assistant/conversations/c1/messages", {
    content: "我腰围 88",
  });
  expect(window.localStorage.getItem("wardrowbe.assistant.conversation")).toBe("c1");
  fireEvent.click(screen.getByRole("button", { name: "confirm" }));
  expect(await screen.findByText("已更新。")).toBeTruthy();
  expect(mocks.post).toHaveBeenCalledWith("/assistant/actions/a1/confirm");
  expect(mocks.stream).toHaveBeenLastCalledWith("/assistant/conversations/c1/continue");
  // The profile query is refreshed so open pages show the change.
  expect(client.invalidateQueries).toHaveBeenCalledWith({ queryKey: ["user-profile"] });
  expect(screen.getByRole("button", { name: /undo/ })).toBeTruthy();
});

it("restores the last conversation and opens with a prepared prompt", async () => {
  window.localStorage.setItem("wardrowbe.assistant.conversation", "c9");
  mocks.get.mockResolvedValue({
    id: "c9",
    messages: [
      { id: "m1", role: "user", content: "hi", created_at: "2026-10-30T10:00:00Z" },
      { id: "m2", role: "assistant", content: "hello", created_at: "2026-10-30T10:00:02Z" },
    ],
    actions: [
      {
        ...pending,
        status: "applied",
        undoable: true,
        tool: "replace_garment",
        result: { id: "r2" },
        created_at: "2026-10-30T10:00:01Z",
      },
    ],
  });
  mount();
  act(() => openAssistant("今天穿什么？"));
  expect(await screen.findByText("hello")).toBeTruthy();
  expect((screen.getByLabelText("placeholder") as HTMLTextAreaElement).value).toBe(
    "今天穿什么？",
  );
  const cards = screen.getAllByTestId("assistant-action");
  expect(cards).toHaveLength(1);
  expect(screen.getByRole("link", { name: "openReport" }).getAttribute("href")).toBe(
    "/dashboard/body-styling?report=r2",
  );
  mocks.post.mockResolvedValue({ ...pending, status: "undone", tool: "replace_garment" });
  fireEvent.click(screen.getByRole("button", { name: /undo/ }));
  await waitFor(() => expect(screen.getByText("status.undone")).toBeTruthy());
  expect(mocks.stream).not.toHaveBeenCalled();
});

it("uploads attached photos and sends them with the message", async () => {
  mocks.post.mockResolvedValue({ id: "c1" });
  mocks.upload
    .mockResolvedValueOnce({ id: "img1" })
    .mockResolvedValueOnce({ id: "img2" });
  mocks.stream.mockReturnValue(
    events(
      { type: "tool", name: "add_wardrobe_item" },
      {
        type: "action",
        action: {
          id: "a2",
          tool: "add_wardrobe_item",
          status: "applied",
          summary: "已加入衣橱：藏青衬衫",
          result: { item_id: "i1", thumbnail_url: "/api/v1/images/t.jpg" },
          undoable: true,
        },
      },
      { type: "message", id: "m1", content: "加好了。" },
    ),
  );
  mount();
  fireEvent.click(screen.getByRole("button", { name: "open" }));
  const input = screen.getByTestId("assistant-file");
  fireEvent.change(input, { target: { files: [photo("a.jpg"), photo("b.jpg"), photo("c.jpg")] } });
  fireEvent.click(screen.getAllByRole("button", { name: "removeImage" })[2]);
  expect(screen.getAllByRole("button", { name: "removeImage" })).toHaveLength(2);
  expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:c.jpg");
  // A photo alone is enough to send.
  fireEvent.click(screen.getByRole("button", { name: "send" }));
  expect(await screen.findByText("加好了。")).toBeTruthy();
  expect(mocks.upload).toHaveBeenCalledTimes(2);
  expect((mocks.upload.mock.calls[0][1] as FormData).get("image")).toBeInstanceOf(File);
  expect(mocks.stream).toHaveBeenCalledWith("/assistant/conversations/c1/messages", {
    content: "",
    image_ids: ["img1", "img2"],
  });
  expect(screen.queryByTestId("assistant-attachments")).toBeNull();
  expect(screen.getAllByAltText("photo")).toHaveLength(2);
  expect(screen.getByRole("link", { name: "openItem" }).getAttribute("href")).toBe(
    "/dashboard/wardrobe?item=i1",
  );
  expect(client.invalidateQueries).toHaveBeenCalledWith({ queryKey: ["items"] });
});

it("limits photos per message and explains a rejected upload", async () => {
  mount();
  fireEvent.click(screen.getByRole("button", { name: "open" }));
  fireEvent.change(screen.getByTestId("assistant-file"), {
    target: { files: ["1", "2", "3", "4", "5"].map((n) => photo(`${n}.jpg`)) },
  });
  expect(screen.getAllByRole("button", { name: "removeImage" })).toHaveLength(4);
  expect(screen.getByRole("alert").textContent).toContain("imageLimit");
  expect(
    (screen.getByRole("button", { name: "attach" }) as HTMLButtonElement).disabled,
  ).toBe(true);
  const { ApiError } = await import("@/lib/api");
  mocks.upload.mockRejectedValue(new ApiError("too big", 413, {}));
  fireEvent.click(screen.getByRole("button", { name: "send" }));
  await waitFor(() =>
    expect(screen.getByRole("alert").textContent).toBe("error.imageTooLarge"),
  );
  expect(mocks.stream).not.toHaveBeenCalled();
});

it("shows photos of a restored conversation", async () => {
  window.localStorage.setItem("wardrowbe.assistant.conversation", "c3");
  mocks.get.mockResolvedValue({
    id: "c3",
    messages: [
      {
        id: "m1",
        role: "user",
        content: "",
        images: [{ id: "img1", thumbnail_url: "/api/v1/images/t1.jpg", url: "/m1.jpg" }],
        created_at: "2026-10-30T10:00:00Z",
      },
    ],
    actions: [],
  });
  mount();
  act(() => openAssistant());
  const image = await screen.findByAltText("photo");
  expect(image.getAttribute("src")).toBe("/api/v1/images/t1.jpg");
});
