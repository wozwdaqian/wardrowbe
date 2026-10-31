"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useSession } from "next-auth/react";
import { api } from "@/lib/api";
import { useSetTokenIfAvailable } from "@/lib/hooks/use-session-token";
import { queryKeys } from "@/lib/hooks/query-keys";
import type { ColorPlan, Garment } from "@/lib/body-styling";
import type { JapaneseStyleId } from "@/lib/generated/japanese-styles";

export type BodyStyleUnread = { unread: number; pending: number };

// Background reports finish while the user is elsewhere; poll faster only while one is running.
export function useBodyStyleUnread() {
  const { status } = useSession();
  useSetTokenIfAvailable();
  return useQuery({
    queryKey: queryKeys.bodyStyling.unread,
    queryFn: () => api.get<BodyStyleUnread>("/body-styling/unread"),
    enabled: status === "authenticated",
    refetchInterval: (query) => (query.state.data?.pending ? 10_000 : 60_000),
    meta: { toastsOwnErrors: true },
  });
}

export type TodayOutfit = {
  date: string;
  occasion: "daily" | "work" | "date" | "weekend" | "formal";
  style: string;
  // The quiz's main Japanese sub-style, when the user saved one.
  style_direction: JapaneseStyleId | null;
  season: "spring" | "summer" | "autumn" | "winter";
  reroll: number;
  weather: {
    temperature: number;
    condition: string;
    location: string | null;
  } | null;
  has_measurements: boolean;
  wardrobe_items: number;
  wardrobe_ready: boolean;
  outfit: {
    title: string;
    garments: Garment[];
    body_reason: string;
    styling_tip: string;
    color_plan: ColorPlan;
    color_reason: string;
    evidence: string[];
  };
};

function todayParams(occasion: string | null, reroll: number) {
  const params: Record<string, string> = { reroll: String(reroll) };
  if (occasion) params.occasion = occasion;
  return params;
}

export function useTodayOutfit(occasion: string | null, reroll: number) {
  const { status } = useSession();
  useSetTokenIfAvailable();
  return useQuery({
    queryKey: queryKeys.bodyStyling.today(occasion, reroll),
    queryFn: () =>
      api.get<TodayOutfit>("/body-styling/today", {
        params: todayParams(occasion, reroll),
      }),
    enabled: status === "authenticated",
    staleTime: 30 * 60_000,
    meta: { toastsOwnErrors: true },
  });
}

export function useExplainToday() {
  return useMutation({
    mutationFn: ({
      occasion,
      reroll,
    }: {
      occasion: string | null;
      reroll: number;
    }) =>
      api.post<{ text: string }>("/body-styling/today/explain", undefined, {
        params: todayParams(occasion, reroll),
      }),
    meta: { toastsOwnErrors: true },
  });
}
