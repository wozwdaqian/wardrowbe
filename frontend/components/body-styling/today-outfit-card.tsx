"use client";

import { useState } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { Bot, Loader2, RefreshCw, Shirt, Sparkles, Wand2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { OutfitIllustration } from "@/components/body-styling/outfit-illustration";
import { openAssistant } from "@/components/assistant/assistant-panel";
import { useExplainToday, useTodayOutfit } from "@/lib/hooks/use-body-styling";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { queryKeys } from "@/lib/hooks/query-keys";
import type { AIStatus } from "@/lib/body-styling";
import { cn } from "@/lib/utils";

const OCCASIONS = ["work", "weekend", "daily", "date", "formal"] as const;

export function TodayOutfitCard() {
  const t = useTranslations("bodyStyling");
  const ta = useTranslations("assistant");
  const [occasion, setOccasion] = useState<string | null>(null);
  const [reroll, setReroll] = useState(0);
  const today = useTodayOutfit(occasion, reroll);
  const explain = useExplainToday();
  const status = useQuery({
    queryKey: queryKeys.bodyStyling.status,
    queryFn: () => api.get<AIStatus>("/body-styling/status"),
    staleTime: 30_000,
    meta: { toastsOwnErrors: true },
  });
  const data = today.data;
  const shown = occasion || data?.occasion;

  function choose(next: string) {
    setOccasion(next);
    setReroll(0);
    explain.reset();
  }

  return (
    <Card
      className="border-emerald-200 bg-emerald-50/40 dark:border-emerald-900 dark:bg-emerald-950/20"
      data-testid="today-outfit"
    >
      <CardHeader className="pb-3">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <CardTitle className="flex items-center gap-2">
              <Sparkles className="h-5 w-5 text-emerald-700" />
              {t("today.title")}
            </CardTitle>
            {data && (
              <CardDescription className="mt-1">
                {data.weather?.location && (
                  <span className="mr-2 font-medium text-foreground">
                    {t("today.weather", {
                      location: data.weather.location,
                      temperature: Math.round(data.weather.temperature),
                    })}
                  </span>
                )}
                {t(
                  data.has_measurements ? "today.basis" : "today.basisNoBody",
                  {
                    season: t("seasons." + data.season),
                  },
                )}
              </CardDescription>
            )}
          </div>
          <div
            className="flex flex-wrap gap-1"
            role="group"
            aria-label={t("occasion")}
          >
            {OCCASIONS.map((value) => (
              <Button
                key={value}
                type="button"
                size="sm"
                variant={shown === value ? "default" : "outline"}
                className={cn(
                  "h-7 px-2.5 text-xs",
                  shown === value && "bg-emerald-800",
                )}
                aria-pressed={shown === value}
                onClick={() => choose(value)}
              >
                {t("occasions." + value)}
              </Button>
            ))}
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {today.isLoading ? (
          <div className="grid gap-4 md:grid-cols-[220px_1fr]">
            <Skeleton className="h-64 w-full" />
            <div className="space-y-2">
              <Skeleton className="h-5 w-2/3" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-5/6" />
            </div>
          </div>
        ) : today.isError || !data ? (
          <p role="alert" className="text-sm text-destructive">
            {t("today.error")}
          </p>
        ) : (
          <div className="grid gap-4 md:grid-cols-[220px_1fr]">
            <OutfitIllustration
              outfit={{
                title: data.outfit.title,
                garments: data.outfit.garments,
                body_reason: data.outfit.body_reason,
                evidence: [],
                styling_tip: data.outfit.styling_tip,
              }}
            />
            <div className="min-w-0 space-y-3">
              <h3 className="font-semibold">{data.outfit.title}</h3>
              <ul className="space-y-1.5 text-sm">
                {data.outfit.garments.map((garment, index) => (
                  <li key={index} className="flex items-start gap-2">
                    <span
                      aria-hidden="true"
                      className="mt-1 h-3.5 w-3.5 shrink-0 rounded-full border border-black/15"
                      style={{ backgroundColor: garment.color }}
                    />
                    {garment.description}
                  </li>
                ))}
              </ul>
              <p className="text-sm leading-6 text-muted-foreground">
                {data.outfit.body_reason}
              </p>
              <p className="text-sm leading-6">{data.outfit.styling_tip}</p>
              {explain.data && (
                <p
                  className="rounded-md bg-background/80 p-3 text-sm leading-6"
                  data-testid="today-explanation"
                >
                  {explain.data.text}
                </p>
              )}
              {explain.isError && (
                <p role="alert" className="text-sm text-destructive">
                  {t("today.explainFailed")}
                </p>
              )}
              <div className="flex flex-wrap gap-2 pt-1">
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  disabled={today.isFetching}
                  onClick={() => {
                    setReroll((value) => value + 1);
                    explain.reset();
                  }}
                >
                  <RefreshCw className="mr-1.5 h-4 w-4" />
                  {t("today.another")}
                </Button>
                {status.data?.available && (
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    disabled={explain.isPending}
                    onClick={() => explain.mutate({ occasion, reroll })}
                  >
                    {explain.isPending ? (
                      <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
                    ) : (
                      <Wand2 className="mr-1.5 h-4 w-4" />
                    )}
                    {t("today.explain")}
                  </Button>
                )}
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  onClick={() => openAssistant(ta("prompts.today"))}
                >
                  <Bot className="mr-1.5 h-4 w-4" />
                  {ta("open")}
                </Button>
                <Button
                  asChild
                  size="sm"
                  className="bg-emerald-800 text-white hover:bg-emerald-900"
                >
                  <Link href="/dashboard/body-styling">
                    {t("today.fullReport")}
                  </Link>
                </Button>
              </div>
              <Link
                href={
                  data.wardrobe_ready
                    ? "/dashboard/suggest"
                    : "/dashboard/wardrobe"
                }
                className="inline-flex items-center gap-1.5 text-xs text-emerald-800 underline-offset-4 hover:underline dark:text-emerald-300"
              >
                <Shirt className="h-3.5 w-3.5" />
                {t(
                  data.wardrobe_ready
                    ? "today.useWardrobe"
                    : "today.addClothes",
                )}
              </Link>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
