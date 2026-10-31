"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { useMutation } from "@tanstack/react-query";
import { ArrowLeft, Loader2, Luggage } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";

const OCCASIONS = ["daily", "work", "date", "weekend", "formal"] as const;
const STYLES = [
  "minimal",
  "smart_casual",
  "street",
  "sporty",
  "classic",
] as const;
type Piece = {
  index: number;
  slot: string;
  kind: string;
  color: string;
  description: string;
  days: string[];
  owned: { id: string; name: string | null; same_color: boolean } | null;
};
type Packing = {
  location: string | null;
  forecast_days: number;
  pieces: Piece[];
  days: {
    date: string;
    occasion: string;
    season: string;
    temp_min: number | null;
    temp_max: number | null;
    pieces: number[];
  }[];
};

function isoDate(offset: number) {
  const day = new Date();
  day.setDate(day.getDate() + offset);
  return day.toISOString().slice(0, 10);
}

export default function PackingPage() {
  const t = useTranslations("bodyStyling");
  const locale = useLocale();
  const [city, setCity] = useState("");
  const [start, setStart] = useState(isoDate(1));
  const [end, setEnd] = useState(isoDate(3));
  const [occasions, setOccasions] = useState<string[]>(["work"]);
  const [style, setStyle] = useState<string>("minimal");
  const [packed, setPacked] = useState<Set<number>>(new Set());
  const plan = useMutation({
    mutationFn: () =>
      api.post<Packing>("/body-styling/packing", {
        start_date: start,
        end_date: end,
        occasions,
        style,
        city: city.trim() || null,
      }),
    onSuccess: () => setPacked(new Set()),
    meta: { toastsOwnErrors: true },
  });
  const code =
    plan.error instanceof ApiError
      ? (plan.error.data as { detail?: { code?: string } })?.detail?.code
      : undefined;

  function toggleOccasion(value: string) {
    setOccasions((current) =>
      current.includes(value)
        ? current.filter((item) => item !== value)
        : [...current, value],
    );
  }
  function submit(event: FormEvent) {
    event.preventDefault();
    if (occasions.length) plan.mutate();
  }
  const dayLabel = (value: string) =>
    new Date(value + "T00:00:00").toLocaleDateString(locale, {
      month: "short",
      day: "numeric",
      weekday: "short",
    });

  return (
    <div className="space-y-6">
      <Link
        href="/dashboard/body-styling"
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" />
        {t("packing.back")}
      </Link>
      <header className="space-y-2">
        <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
          <Luggage className="h-6 w-6 text-emerald-700" />
          {t("packing.title")}
        </h1>
        <p className="max-w-2xl text-sm leading-7 text-muted-foreground">
          {t("packing.intro")}
        </p>
      </header>
      <div className="grid gap-6 lg:grid-cols-[340px_1fr]">
        <Card>
          <CardContent className="pt-6">
            <form className="space-y-4" onSubmit={submit}>
              <label className="block space-y-1.5 text-sm">
                <span className="font-medium">{t("packing.city")}</span>
                <Input
                  value={city}
                  placeholder={t("packing.cityPlaceholder")}
                  onChange={(e) => setCity(e.target.value)}
                  maxLength={100}
                />
              </label>
              <div className="grid grid-cols-2 gap-3">
                <label className="block space-y-1.5 text-sm">
                  <span className="font-medium">{t("packing.start")}</span>
                  <Input
                    type="date"
                    required
                    value={start}
                    onChange={(e) => setStart(e.target.value)}
                  />
                </label>
                <label className="block space-y-1.5 text-sm">
                  <span className="font-medium">{t("packing.end")}</span>
                  <Input
                    type="date"
                    required
                    min={start}
                    value={end}
                    onChange={(e) => setEnd(e.target.value)}
                  />
                </label>
              </div>
              <fieldset className="space-y-2">
                <legend className="text-sm font-medium">
                  {t("packing.occasions")}
                </legend>
                <div className="flex flex-wrap gap-2">
                  {OCCASIONS.map((value) => (
                    <Button
                      key={value}
                      type="button"
                      size="sm"
                      variant={
                        occasions.includes(value) ? "default" : "outline"
                      }
                      aria-pressed={occasions.includes(value)}
                      onClick={() => toggleOccasion(value)}
                    >
                      {t("occasions." + value)}
                    </Button>
                  ))}
                </div>
                <p className="text-xs text-muted-foreground">
                  {t("packing.occasionsHelp")}
                </p>
              </fieldset>
              <label className="block space-y-1.5 text-sm">
                <span className="font-medium">{t("style")}</span>
                <select
                  value={style}
                  onChange={(e) => setStyle(e.target.value)}
                  className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                >
                  {STYLES.map((value) => (
                    <option key={value} value={value}>
                      {t("styles." + value)}
                    </option>
                  ))}
                </select>
              </label>
              <Button
                type="submit"
                className="w-full bg-emerald-800 text-white hover:bg-emerald-900"
                disabled={plan.isPending || !occasions.length}
              >
                {plan.isPending && (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                )}
                {t("packing.submit")}
              </Button>
              {plan.isError && (
                <p role="alert" className="text-sm text-destructive">
                  {t(
                    code === "unknown_city"
                      ? "packing.unknownCity"
                      : "packing.error",
                  )}
                </p>
              )}
            </form>
          </CardContent>
        </Card>
        {plan.data && (
          <div className="space-y-6" data-testid="packing-result">
            <Card>
              <CardHeader>
                <CardTitle>
                  {t("packing.listTitle", {
                    count: plan.data.pieces.length,
                    days: plan.data.days.length,
                  })}
                </CardTitle>
                <CardDescription>
                  {plan.data.forecast_days
                    ? t("packing.forecast", {
                        location: plan.data.location || "",
                      })
                    : t("packing.noForecast")}
                </CardDescription>
              </CardHeader>
              <CardContent>
                <ul className="space-y-3">
                  {plan.data.pieces.map((piece) => (
                    <li key={piece.index} className="flex items-start gap-3">
                      <Checkbox
                        id={`piece-${piece.index}`}
                        checked={packed.has(piece.index)}
                        onCheckedChange={(checked) =>
                          setPacked((current) => {
                            const next = new Set(current);
                            if (checked) next.add(piece.index);
                            else next.delete(piece.index);
                            return next;
                          })
                        }
                        className="mt-1"
                      />
                      <span
                        aria-hidden="true"
                        className="mt-1 h-4 w-4 shrink-0 rounded-full border border-black/15"
                        style={{ backgroundColor: piece.color }}
                      />
                      <label
                        htmlFor={`piece-${piece.index}`}
                        className={
                          "min-w-0 text-sm leading-6 " +
                          (packed.has(piece.index)
                            ? "text-muted-foreground line-through"
                            : "")
                        }
                      >
                        {piece.description}
                        <span className="block text-xs text-muted-foreground">
                          {t("packing.wornOn", { count: piece.days.length })}
                          {" · "}
                          {piece.owned
                            ? t(
                                piece.owned.same_color
                                  ? "packing.owned"
                                  : "packing.ownedOtherColor",
                                {
                                  name:
                                    piece.owned.name ||
                                    t("wardrobe.itemFallback"),
                                },
                              )
                            : t("packing.toBuy")}
                        </span>
                      </label>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">
                  {t("packing.daysTitle")}
                </CardTitle>
              </CardHeader>
              <CardContent>
                <ol className="space-y-3">
                  {plan.data.days.map((day) => (
                    <li key={day.date} className="rounded-lg border p-3">
                      <p className="text-sm font-medium">
                        {dayLabel(day.date)} · {t("occasions." + day.occasion)}
                        {" · "}
                        {t("seasons." + day.season)}
                        {day.temp_min !== null && day.temp_max !== null && (
                          <span className="text-muted-foreground">
                            {" "}
                            {Math.round(day.temp_min)}–
                            {Math.round(day.temp_max)}°C
                          </span>
                        )}
                      </p>
                      <p className="mt-1 text-sm text-muted-foreground">
                        {day.pieces
                          .map((index) => plan.data.pieces[index].description)
                          .join(" / ")}
                      </p>
                    </li>
                  ))}
                </ol>
              </CardContent>
            </Card>
          </div>
        )}
      </div>
    </div>
  );
}
