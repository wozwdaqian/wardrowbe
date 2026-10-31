import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import BodyStylingPage from "@/app/dashboard/body-styling/page";
import type { UserProfile } from "@/lib/hooks/use-user";

const mocks = vi.hoisted(() => ({
  profile: null as UserProfile | null,
  mutate: vi.fn(),
  refetch: vi.fn(),
  search: new URLSearchParams(),
  // Mirrors the router: replacing the URL changes what useSearchParams returns.
  replace: vi.fn((url: string) => {
    mocks.search = new URLSearchParams(url.split("?")[1] || "");
  }),
  post: vi.fn(),
  get: vi.fn(),
  delete: vi.fn(),
}));
vi.mock("next-intl", () => ({
  useLocale: () => "zh-CN",
  useTranslations: () => (key: string) => key,
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: mocks.replace }),
  useSearchParams: () => mocks.search,
}));
vi.mock("@/lib/hooks/use-user", () => ({
  useUserProfile: () => ({
    data: mocks.profile,
    isError: false,
    refetch: mocks.refetch,
  }),
  useUpdateUserProfile: () => ({ mutateAsync: mocks.mutate, isPending: false }),
}));
vi.mock("@/lib/api", async (original) => ({
  ...(await original<typeof import("@/lib/api")>()),
  api: { get: mocks.get, post: mocks.post, delete: mocks.delete },
}));

function profile(waist = 90, revision = "a".repeat(64)): UserProfile {
  return {
    id: "test-user",
    email: "body-test@example.com",
    display_name: "Test",
    timezone: "UTC",
    locale: "zh-CN",
    role: "user",
    onboarding_completed: true,
    body_measurements: { height: 175, chest: 100, waist, hips: 102 },
    body_measurements_revision: revision,
    styling_profile: {},
    styling_profile_revision: revision,
  };
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}
function mount() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <BodyStylingPage />
    </QueryClientProvider>,
  );
}
beforeEach(() => {
  vi.clearAllMocks();
  mocks.search = new URLSearchParams();
  mocks.profile = profile();
  mocks.mutate.mockImplementation(async () => mocks.profile);
  mocks.get.mockImplementation(async (path: string) =>
    path.endsWith("/status")
      ? { enabled: true, configured: true, available: true }
      : { items: [], total: 0, limit: 10, offset: 0 },
  );
});

it("refreshes an untouched form with the newest measurements", async () => {
  const view = mount();
  const waist = screen.getByLabelText(/fields.waist/) as HTMLInputElement;
  await waitFor(() => expect(waist.value).toBe("90"));
  mocks.profile = profile(82, "b".repeat(64));
  mocks.profile.body_measurements!.weight = 78;
  view.rerender(
    <QueryClientProvider client={new QueryClient()}>
      <BodyStylingPage />
    </QueryClientProvider>,
  );
  await waitFor(() => expect(waist.value).toBe("82"));
  expect(
    (screen.getByLabelText(/fields.weight/) as HTMLInputElement).value,
  ).toBe("78");
});

it("preserves unsaved edits and submits their original revision after an external change", async () => {
  const view = mount();
  const waist = screen.getByLabelText(/fields.waist/) as HTMLInputElement;
  fireEvent.change(waist, { target: { value: "88" } });
  mocks.profile = profile(82, "b".repeat(64));
  view.rerender(
    <QueryClientProvider client={new QueryClient()}>
      <BodyStylingPage />
    </QueryClientProvider>,
  );
  expect(waist.value).toBe("88");
  expect(screen.getByText("error.body_measurements_conflict")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "save" }));
  await waitFor(() =>
    expect(mocks.mutate).toHaveBeenCalledWith({
      body_measurements: { height: 175, chest: 100, waist: 88, hips: 102 },
      expected_body_measurements_revision: "a".repeat(64),
      styling_profile: {},
      expected_styling_profile_revision: "a".repeat(64),
    }),
  );
});

it("aborts a pending generation and never navigates when its response arrives after leaving", async () => {
  const pending = deferred<{ id: string }>();
  mocks.post.mockReturnValue(pending.promise);
  const view = mount();
  const generate = screen.getByRole("button", {
    name: "generate",
  });
  await waitFor(() => expect(generate).not.toBeDisabled());
  fireEvent.click(generate);
  await waitFor(() => expect(mocks.post).toHaveBeenCalledOnce());
  const signal = mocks.post.mock.calls[0][2].signal as AbortSignal;
  expect(mocks.post.mock.calls[0][1].body_measurements_revision).toBe(
    "a".repeat(64),
  );
  view.unmount();
  expect(signal.aborted).toBe(true);
  await act(async () => {
    pending.resolve({ id: "late-response" });
    await pending.promise;
  });
  expect(mocks.replace).not.toHaveBeenCalled();
});

it("does not start generation if the user leaves while profile saving is pending", async () => {
  const pending = deferred<UserProfile>();
  mocks.mutate.mockReturnValue(pending.promise);
  const view = mount();
  const generate = screen.getByRole("button", {
    name: "generate",
  });
  await waitFor(() => expect(generate).not.toBeDisabled());
  fireEvent.click(generate);
  await waitFor(() => expect(mocks.mutate).toHaveBeenCalledOnce());
  view.unmount();
  await act(async () => {
    pending.resolve(profile());
    await pending.promise;
  });
  expect(mocks.post).not.toHaveBeenCalled();
  expect(mocks.replace).not.toHaveBeenCalled();
});

it("saves optional coloring and fabric preferences with the body profile", async () => {
  mount();
  // The personal section starts collapsed and shows how many fields are filled.
  expect(screen.queryByLabelText("personal.skin_depth")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: /personalSection/ }));
  fireEvent.change(screen.getByLabelText("personal.skin_depth"), {
    target: { value: "tan" },
  });
  fireEvent.change(screen.getByLabelText("personal.undertone"), {
    target: { value: "warm" },
  });
  fireEvent.click(screen.getByTestId("preferred_color_families-blue"));
  fireEvent.click(screen.getByTestId("avoided_materials-wool"));
  fireEvent.click(screen.getByRole("button", { name: "save" }));
  await waitFor(() =>
    expect(mocks.mutate).toHaveBeenCalledWith(
      expect.objectContaining({
        styling_profile: {
          skin_depth: "tan",
          undertone: "warm",
          preferred_color_families: ["blue"],
          avoided_color_families: [],
          avoided_materials: ["wool"],
        },
        expected_styling_profile_revision: "a".repeat(64),
      }),
    ),
  );
});

it("detects a preference-only conflict while retaining local edits", async () => {
  const view = mount();
  fireEvent.click(screen.getByRole("button", { name: /personalSection/ }));
  fireEvent.change(screen.getByLabelText("personal.hair_color"), {
    target: { value: "black" },
  });
  mocks.profile = {
    ...profile(),
    styling_profile: { hair_color: "grey" },
    styling_profile_revision: "b".repeat(64),
  };
  view.rerender(
    <QueryClientProvider client={new QueryClient()}>
      <BodyStylingPage />
    </QueryClientProvider>,
  );
  expect(
    (screen.getByLabelText("personal.hair_color") as HTMLSelectElement).value,
  ).toBe("black");
  expect(screen.getByText("error.body_measurements_conflict")).toBeTruthy();
});

it("still generates rule-based looks when no AI is configured", async () => {
  mocks.get.mockImplementation(async (path: string) =>
    path.endsWith("/status")
      ? { enabled: true, configured: false, available: false }
      : { items: [], total: 0, limit: 10, offset: 0 },
  );
  mocks.post.mockReturnValue(new Promise(() => {}));
  mount();
  expect(await screen.findByTestId("ai-unavailable")).toBeTruthy();
  const generate = screen.getByRole("button", { name: "generate" });
  await waitFor(() => expect(generate).not.toBeDisabled());
  fireEvent.click(generate);
  await waitFor(() => expect(mocks.post).toHaveBeenCalledOnce());
  expect(mocks.post.mock.calls[0][1].mode).toBe("auto");
  expect(screen.queryByRole("button", { name: "generateRules" })).toBeNull();
});

it("deletes a history report only after confirming", async () => {
  mocks.get.mockImplementation(async (path: string) =>
    path.endsWith("/status")
      ? { enabled: true, configured: true, available: true }
      : {
          items: [
            {
              id: "r1",
              created_at: "2026-10-30T10:00:00Z",
              summary: "Old report",
              context: {
                occasion: "daily",
                style: "minimal",
                goals: ["comfort"],
                season: "all",
              },
            },
          ],
          total: 1,
          limit: 10,
          offset: 0,
        },
  );
  mocks.delete.mockResolvedValue(undefined);
  mount();
  fireEvent.click(await screen.findByRole("button", { name: "deleteReport" }));
  expect(mocks.delete).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "confirmDelete" }));
  await waitFor(() =>
    expect(mocks.delete).toHaveBeenCalledWith(
      "/body-styling/recommendations/r1",
    ),
  );
});

const pendingReport = {
  id: "bg1",
  created_at: "2026-10-30T10:00:00Z",
  model: null,
  status: "pending",
  input_snapshot: {
    measurements: {},
    context: {
      occasion: "work",
      style: "classic",
      goals: ["comfort"],
      season: "winter",
    },
  },
  facts: [],
  result: null,
};

it("polls a background report and shows it once finished", async () => {
  mocks.post.mockResolvedValue(pendingReport);
  let finished = false;
  mocks.get.mockImplementation(async (path: string) => {
    if (path.endsWith("/status"))
      return { enabled: true, configured: true, available: true };
    if (path.endsWith("/bg1"))
      return finished
        ? { ...pendingReport, status: "done", result: null, error_code: null }
        : pendingReport;
    return { items: [], total: 0, limit: 10, offset: 0 };
  });
  mount();
  const generate = screen.getByRole("button", { name: "generate" });
  await waitFor(() => expect(generate).not.toBeDisabled());
  fireEvent.click(generate);
  expect(await screen.findByTestId("report-pending")).toBeTruthy();
  finished = true;
  await waitFor(
    () => expect(screen.queryByTestId("report-pending")).toBeNull(),
    { timeout: 5000 },
  );
  const detailCalls = mocks.get.mock.calls.filter(([path]) =>
    String(path).endsWith("/bg1"),
  );
  expect(detailCalls.length).toBeGreaterThanOrEqual(2);
}, 10000);

it("explains a failed report and retries with its original settings", async () => {
  const failedReport = {
    ...pendingReport,
    status: "failed",
    error_code: "ai_timeout",
  };
  mocks.post.mockResolvedValueOnce(failedReport);
  mocks.get.mockImplementation(async (path: string) =>
    path.endsWith("/status")
      ? { enabled: true, configured: true, available: true }
      : path.endsWith("/bg1")
        ? failedReport
        : { items: [], total: 0, limit: 10, offset: 0 },
  );
  mount();
  const generate = screen.getByRole("button", { name: "generate" });
  await waitFor(() => expect(generate).not.toBeDisabled());
  fireEvent.click(generate);
  const failed = await screen.findByTestId("report-failed");
  expect(failed.textContent).toContain("error.ai_timeout");
  mocks.post.mockReturnValue(new Promise(() => {}));
  fireEvent.click(screen.getByRole("button", { name: "retry" }));
  await waitFor(() => expect(mocks.post).toHaveBeenCalledTimes(2));
  expect(mocks.post.mock.calls[1][1]).toMatchObject({
    occasion: "work",
    season: "winter",
    mode: "auto",
  });
});
