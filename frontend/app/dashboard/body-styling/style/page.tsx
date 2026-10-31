"use client";

import { useState } from "react";
import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Bot,
  Check,
  Compass,
  Copy,
  Heart,
  Loader2,
  Minus,
  RotateCcw,
  ThumbsDown,
} from "lucide-react";
import { api } from "@/lib/api";
import { queryKeys } from "@/lib/hooks/query-keys";
import { useUserProfile } from "@/lib/hooks/use-user";
import {
  asOutfit,
  styleName,
  type Answer,
  type StyleCard,
  type StyleDetail,
  type StyleResult,
} from "@/lib/style-explore";
import type { JapaneseStyleId } from "@/lib/generated/japanese-styles";
import { OutfitIllustration } from "@/components/body-styling/outfit-illustration";
import { openAssistant } from "@/components/assistant/assistant-panel";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { cn } from "@/lib/utils";

type Stage = "intro" | "round1" | "round2" | "result";
const BASE = "/body-styling/style-explore";

export default function StyleExplorePage() {
  const t = useTranslations("bodyStyling.styleExplore");
  const locale = useLocale();
  const queryClient = useQueryClient();
  const { data: profile } = useUserProfile();
  const current = profile?.styling_profile?.preferred_styles || [];
  const [stage, setStage] = useState<Stage>("intro");
  const [cards, setCards] = useState<StyleCard[]>([]);
  const [position, setPosition] = useState(0);
  const [answers, setAnswers] = useState<Record<string, Answer>>({});
  const [result, setResult] = useState<StyleResult | null>(null);
  const [saved, setSaved] = useState<JapaneseStyleId[] | null>(null);

  const start = useMutation({
    mutationFn: () =>
      api.get<{ cards: StyleCard[] }>(`${BASE}/round-one`),
    onSuccess: (data) => {
      setAnswers({});
      setResult(null);
      setSaved(null);
      setCards(data.cards);
      setPosition(0);
      setStage("round1");
    },
    meta: { toastsOwnErrors: true },
  });
  const deeper = useMutation({
    mutationFn: (all: Record<string, Answer>) =>
      api.post<{ cards: StyleCard[] }>(`${BASE}/round-two`, { answers: all }),
    onSuccess: (data, all) => {
      if (!data.cards.length) return finish.mutate(all);
      setCards(data.cards);
      setPosition(0);
      setStage("round2");
    },
    meta: { toastsOwnErrors: true },
  });
  const finish = useMutation({
    mutationFn: (all: Record<string, Answer>) =>
      api.post<StyleResult>(`${BASE}/result`, { answers: all }),
    onSuccess: (data) => {
      setResult(data);
      setStage("result");
    },
    meta: { toastsOwnErrors: true },
  });
  const save = useMutation({
    mutationFn: (styles: JapaneseStyleId[]) =>
      api.patch<{ preferred_styles: JapaneseStyleId[] }>(`${BASE}/styles`, {
        styles,
      }),
    onSuccess: (data) => {
      setSaved(data.preferred_styles);
      queryClient.invalidateQueries({ queryKey: queryKeys.userProfile });
      queryClient.invalidateQueries({
        queryKey: queryKeys.bodyStyling.todayAll,
      });
    },
    meta: { toastsOwnErrors: true },
  });
  const busy = start.isPending || deeper.isPending || finish.isPending;
  const failed = start.isError || deeper.isError || finish.isError;

  function answer(value: Answer) {
    const card = cards[position];
    const next = { ...answers, [card.id]: value };
    setAnswers(next);
    if (position + 1 < cards.length) setPosition(position + 1);
    else if (stage === "round1") deeper.mutate(next);
    else finish.mutate(next);
  }

  return (
    <div className="mx-auto max-w-3xl space-y-5 pb-24">
      <div className="flex items-center gap-2">
        <Button asChild variant="ghost" size="icon" aria-label={t("back")}>
          <Link href="/dashboard/body-styling">
            <ArrowLeft className="h-4 w-4" />
          </Link>
        </Button>
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold">
            <Compass className="h-6 w-6 text-emerald-700" />
            {t("title")}
          </h1>
          <p className="text-sm text-muted-foreground">{t("subtitle")}</p>
        </div>
      </div>

      {failed && (
        <p role="alert" className="text-sm text-destructive">
          {t("error")}
        </p>
      )}

      {stage === "intro" && (
        <Card>
          <CardContent className="space-y-4 pt-6">
            <p className="leading-7">{t("intro")}</p>
            <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
              <li>{t("howRoundOne")}</li>
              <li>{t("howRoundTwo")}</li>
              <li>{t("howResult")}</li>
            </ul>
            {!!current.length && (
              <p className="text-sm" data-testid="current-styles">
                {t("current", {
                  styles: current.map((id) => styleName(id, locale)).join(" · "),
                })}
              </p>
            )}
            <Button onClick={() => start.mutate()} disabled={busy}>
              {start.isPending && (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              )}
              {current.length ? t("retake") : t("start")}
            </Button>
          </CardContent>
        </Card>
      )}

      {(stage === "round1" || stage === "round2") && cards[position] && (
        <QuizCard
          card={cards[position]}
          stage={stage}
          position={position}
          total={cards.length}
          busy={busy}
          onAnswer={answer}
          onBack={position > 0 ? () => setPosition(position - 1) : undefined}
        />
      )}

      {busy && stage !== "intro" && (
        <p
          role="status"
          className="flex items-center gap-2 text-sm text-muted-foreground"
        >
          <Loader2 className="h-4 w-4 animate-spin" />
          {t("calculating")}
        </p>
      )}

      {stage === "result" && result && (
        <ResultView
          result={result}
          saved={saved}
          saving={save.isPending}
          onSave={() => save.mutate(result.styles.map((s) => s.id))}
          onRetake={() => start.mutate()}
        />
      )}
    </div>
  );
}

function QuizCard({
  card,
  stage,
  position,
  total,
  busy,
  onAnswer,
  onBack,
}: {
  card: StyleCard;
  stage: "round1" | "round2";
  position: number;
  total: number;
  busy: boolean;
  onAnswer: (value: Answer) => void;
  onBack?: () => void;
}) {
  const t = useTranslations("bodyStyling.styleExplore");
  return (
    <Card data-testid="quiz-card">
      <CardHeader className="space-y-2">
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>{stage === "round1" ? t("roundOne") : t("roundTwo")}</span>
          <span>{t("progress", { current: position + 1, total })}</span>
        </div>
        <Progress value={((position + 1) / total) * 100} />
        <CardTitle className="pt-2 text-lg">{card.title}</CardTitle>
        <div className="flex flex-wrap gap-1.5">
          {card.tags.map((tag) => (
            <Badge key={tag} variant="secondary">
              {tag}
            </Badge>
          ))}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="mx-auto max-w-xs">
          <OutfitIllustration outfit={asOutfit(card)} />
        </div>
        <ul className="space-y-1 text-sm text-muted-foreground">
          {card.garments.map((garment, index) => (
            <li key={index}>{garment.description}</li>
          ))}
        </ul>
        <div className="grid grid-cols-3 gap-2">
          <Button
            variant="outline"
            disabled={busy}
            onClick={() => onAnswer("dislike")}
          >
            <ThumbsDown className="mr-1.5 h-4 w-4" />
            {t("dislike")}
          </Button>
          <Button
            variant="outline"
            disabled={busy}
            onClick={() => onAnswer("neutral")}
          >
            <Minus className="mr-1.5 h-4 w-4" />
            {t("neutral")}
          </Button>
          <Button
            disabled={busy}
            onClick={() => onAnswer("like")}
            className="bg-emerald-800 hover:bg-emerald-900"
          >
            <Heart className="mr-1.5 h-4 w-4" />
            {t("like")}
          </Button>
        </div>
        {onBack && (
          <Button variant="ghost" size="sm" onClick={onBack} disabled={busy}>
            <ArrowLeft className="mr-1.5 h-4 w-4" />
            {t("previous")}
          </Button>
        )}
      </CardContent>
    </Card>
  );
}

function ResultView({
  result,
  saved,
  saving,
  onSave,
  onRetake,
}: {
  result: StyleResult;
  saved: JapaneseStyleId[] | null;
  saving: boolean;
  onSave: () => void;
  onRetake: () => void;
}) {
  const t = useTranslations("bodyStyling.styleExplore");
  const names = result.styles.map((s) => s.name).join(" · ");
  return (
    <div className="space-y-5" data-testid="style-result">
      <Card className="border-emerald-200 bg-emerald-50/50 dark:border-emerald-900 dark:bg-emerald-950/20">
        <CardHeader>
          <CardDescription>
            {result.confident ? t("resultTitle") : t("unsure")}
          </CardDescription>
          <CardTitle className="text-2xl">{names}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {result.body_note && (
            <p className="text-sm text-muted-foreground">
              {t(`bodyNote.${result.body_note.kind}`)}
            </p>
          )}
          {!!result.liked_colors.length && (
            <p className="text-sm">
              {t("likedColors", { colors: result.liked_colors.join("、") })}
            </p>
          )}
          <div className="flex flex-wrap gap-2">
            {saved ? (
              <p className="flex items-center gap-1.5 text-sm font-medium text-emerald-800 dark:text-emerald-300">
                <Check className="h-4 w-4" />
                {t("saved")}
              </p>
            ) : (
              <Button onClick={onSave} disabled={saving}>
                {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                {t("save")}
              </Button>
            )}
            <Button asChild variant="outline">
              <Link href="/dashboard/body-styling">{t("report")}</Link>
            </Button>
            <Button
              variant="outline"
              onClick={() =>
                openAssistant(t("askPrompt", { style: names }))
              }
            >
              <Bot className="mr-1.5 h-4 w-4" />
              {t("ask")}
            </Button>
            <Button variant="ghost" onClick={onRetake}>
              <RotateCcw className="mr-1.5 h-4 w-4" />
              {t("retake")}
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">{t("saveHint")}</p>
        </CardContent>
      </Card>

      {result.styles.map((style, index) => (
        <StyleSection
          key={style.id}
          style={style}
          label={index === 0 ? t("mainStyle") : t("secondStyle")}
        />
      ))}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("ranking")}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2.5">
          {result.ranking.map((row) => (
            <div key={row.id} className="space-y-1" data-testid="ranking-row">
              <div className="flex items-baseline justify-between gap-2 text-sm">
                <span className="font-medium">{row.name}</span>
                <span className="text-xs text-muted-foreground">
                  {row.tagline}
                </span>
              </div>
              <Progress value={row.score} />
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}

function StyleSection({ style, label }: { style: StyleDetail; label: string }) {
  const t = useTranslations("bodyStyling.styleExplore");
  const [copied, setCopied] = useState<string | null>(null);
  async function copy(term: string) {
    try {
      await navigator.clipboard.writeText(term);
      setCopied(term);
    } catch {
      // Clipboard access can be refused; the term is still visible to copy by hand.
    }
  }
  return (
    <Card data-testid="style-section">
      <CardHeader>
        <CardDescription>{label}</CardDescription>
        <CardTitle className="text-xl">
          {style.name}
          <span className="ml-2 text-sm font-normal text-muted-foreground">
            {style.name_ja}
          </span>
        </CardTitle>
        <p className="text-sm font-medium text-emerald-800 dark:text-emerald-300">
          {style.tagline}
        </p>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="grid gap-4 sm:grid-cols-[1fr_200px]">
          <div className="space-y-3">
            <p className="leading-7">{style.description}</p>
            <div className="flex flex-wrap gap-1.5">
              {style.keywords.map((word) => (
                <Badge key={word} variant="secondary">
                  {word}
                </Badge>
              ))}
            </div>
          </div>
          {style.sample && (
            <div className="mx-auto w-full max-w-[200px]">
              <OutfitIllustration outfit={asOutfit(style.sample)} />
            </div>
          )}
        </div>

        <Section title={t("tips")} items={style.tips} />
        <Section title={t("pitfalls")} items={style.pitfalls} />

        <div className="space-y-2">
          <h3 className="text-sm font-semibold">{t("starter")}</h3>
          <p className="text-xs text-muted-foreground">{t("starterHint")}</p>
          <ul className="space-y-1.5">
            {style.starter.map((piece, index) => (
              <li
                key={index}
                className="flex items-start justify-between gap-3 rounded-lg border px-3 py-2 text-sm"
                data-testid="starter-piece"
              >
                <span className="flex items-start gap-2">
                  <span
                    className="mt-1 h-3 w-3 shrink-0 rounded-full border"
                    style={{ backgroundColor: piece.color }}
                    aria-hidden
                  />
                  <span>
                    {piece.description}
                    {!!piece.matches.length && (
                      <span className="block text-xs text-muted-foreground">
                        {piece.matches
                          .map((m) => m.name)
                          .filter(Boolean)
                          .join("、")}
                      </span>
                    )}
                  </span>
                </span>
                <Badge
                  variant={piece.status === "missing" ? "outline" : "secondary"}
                  className={cn(
                    "shrink-0",
                    piece.status === "owned" &&
                      "bg-emerald-100 text-emerald-900 dark:bg-emerald-900/40 dark:text-emerald-200",
                  )}
                >
                  {t(`status.${piece.status}`)}
                </Badge>
              </li>
            ))}
          </ul>
        </div>

        <div className="space-y-2">
          <h3 className="text-sm font-semibold">{t("search")}</h3>
          <div className="flex flex-wrap gap-2">
            {[...style.search.zh, ...style.search.ja].map((term) => (
              <Button
                key={term}
                type="button"
                variant="outline"
                size="sm"
                onClick={() => copy(term)}
                aria-label={t("copy", { term })}
              >
                {copied === term ? (
                  <Check className="mr-1.5 h-3.5 w-3.5" />
                ) : (
                  <Copy className="mr-1.5 h-3.5 w-3.5" />
                )}
                {term}
              </Button>
            ))}
          </div>
        </div>

        <div className="space-y-1">
          <h3 className="text-sm font-semibold">{t("brands")}</h3>
          <p className="text-sm text-muted-foreground">
            {style.brands.join(" · ")}
          </p>
        </div>
      </CardContent>
    </Card>
  );
}

function Section({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="space-y-1.5">
      <h3 className="text-sm font-semibold">{title}</h3>
      <ul className="list-disc space-y-1 pl-5 text-sm leading-6">
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  );
}
