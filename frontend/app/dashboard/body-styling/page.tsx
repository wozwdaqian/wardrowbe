"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import {
  ArrowRight,
  Check,
  CheckCircle2,
  Clock3,
  Loader2,
  Ruler,
  Sparkles,
} from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { queryKeys } from "@/lib/hooks/query-keys";
import {
  useUserProfile,
  useUpdateUserProfile,
  UserProfile,
} from "@/lib/hooks/use-user";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { OutfitIllustration } from "@/components/body-styling/outfit-illustration";
import { StylingProfileEditor } from "@/components/body-styling/styling-profile-editor";
import { OutfitFeedback } from "@/components/body-styling/outfit-feedback";
import {
  AIStatus,
  BodyStyleHistory,
  BodyStyleReport,
  Context,
  DEFAULT_CONTEXT,
  Fact,
  FactId,
  Goal,
  MEASUREMENT_FIELDS,
  StylingProfile,
  PROFILE_CATALOGS,
  catalogLabel,
} from "@/lib/body-styling";

const occasionKeys: Context["occasion"][] = [
  "daily",
  "work",
  "date",
  "weekend",
  "formal",
];
const styleKeys: Context["style"][] = [
  "minimal",
  "smart_casual",
  "street",
  "sporty",
  "classic",
];
const seasonKeys: Context["season"][] = [
  "all",
  "spring",
  "summer",
  "autumn",
  "winter",
];
const goalKeys: Goal[] = [
  "balance",
  "elongate_legs",
  "midsection",
  "shoulders",
  "comfort",
];

export default function BodyStylingPage() {
  const t = useTranslations("bodyStyling");
  const locale = useLocale();
  const router = useRouter();
  const params = useSearchParams();
  const queryClient = useQueryClient();
  const {
    data: profile,
    isError: profileError,
    refetch: refetchProfile,
  } = useUserProfile();
  const updateProfile = useUpdateUserProfile({ toastsOwnErrors: true });
  const baseProfile = useRef<UserProfile | null>(null);
  const dirty = useRef(false);
  const mounted = useRef(false);
  const generationRequest = useRef<AbortController | null>(null);
  const [conflict, setConflict] = useState(false);
  const formRef = useRef<HTMLFormElement>(null);
  const [measurements, setMeasurements] = useState<Record<string, string>>({});
  const [stylingProfile, setStylingProfile] = useState<StylingProfile>({});
  const [context, setContext] = useState<Context>(DEFAULT_CONTEXT);
  const [selectedId, setSelectedId] = useState<string | null>(
    params.get("report"),
  );
  const [offset, setOffset] = useState(0);
  const [generating, setGenerating] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");
  const active = !!profile;
  const status = useQuery({
    queryKey: queryKeys.bodyStyling.status,
    queryFn: () => api.get<AIStatus>("/body-styling/status"),
    enabled: active,
    staleTime: 30_000,
    meta: { toastsOwnErrors: true },
  });
  const history = useQuery({
    queryKey: queryKeys.bodyStyling.history.page(offset),
    queryFn: () =>
      api.get<BodyStyleHistory>("/body-styling/recommendations", {
        params: { limit: "10", offset: String(offset) },
      }),
    enabled: active,
    meta: { toastsOwnErrors: true },
  });
  const detail = useQuery({
    queryKey: queryKeys.bodyStyling.report(selectedId),
    queryFn: () =>
      api.get<BodyStyleReport>("/body-styling/recommendations/" + selectedId),
    enabled: active && !!selectedId,
    retry: false,
    staleTime: Infinity,
    meta: { toastsOwnErrors: true },
  });

  function loadMeasurements(value: UserProfile) {
    baseProfile.current = value;
    dirty.current = false;
    const values: Record<string, string> = {};
    for (const key of [...MEASUREMENT_FIELDS, "shoulder_type"]) {
      const measurement = value.body_measurements?.[key];
      if (measurement != null) values[key] = String(measurement);
    }
    setMeasurements(values);
    setStylingProfile(value.styling_profile || {});
    setConflict(false);
  }
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      generationRequest.current?.abort();
    };
  }, []);
  useEffect(() => {
    if (!profile) return;
    if (baseProfile.current?.id !== profile.id || !dirty.current) {
      loadMeasurements(profile);
    } else if (
      baseProfile.current.body_measurements_revision !==
        profile.body_measurements_revision ||
      baseProfile.current.styling_profile_revision !==
        profile.styling_profile_revision
    ) {
      setConflict(true);
    }
  }, [profile]);
  useEffect(() => {
    setSelectedId(params.get("report"));
  }, [params]);

  const friendlyError = (err: unknown, fallback = "generic") => {
    const code =
      err instanceof ApiError
        ? (err.data as { detail?: { code?: string } })?.detail?.code
        : undefined;
    return t(
      "error." +
        ([
          "ai_unavailable",
          "invalid_measurements",
          "invalid_ai_response",
          "ai_timeout",
          "ai_failed",
          "body_measurements_conflict",
        ].includes(code || "")
          ? code
          : fallback),
    );
  };
  function changeMeasurement(key: string, value: string) {
    dirty.current = true;
    setMeasurements((previous) => ({ ...previous, [key]: value }));
    setSaved(false);
    setError("");
  }
  function validateMeasurements() {
    if (!formRef.current?.reportValidity()) {
      setError(t("formInvalid"));
      return false;
    }
    if (
      measurements.inseam &&
      Number(measurements.inseam) >= Number(measurements.height)
    ) {
      setError(t("inseamInvalid"));
      return false;
    }
    return true;
  }
  async function persistMeasurements() {
    const base = baseProfile.current;
    if (!base) throw new Error("Profile unavailable");
    const merged: Record<string, number | string> = {
      ...(base.body_measurements || {}),
    };
    for (const key of MEASUREMENT_FIELDS) {
      if (measurements[key]?.trim()) merged[key] = Number(measurements[key]);
      else delete merged[key];
    }
    if (measurements.shoulder_type)
      merged.shoulder_type = measurements.shoulder_type;
    else delete merged.shoulder_type;
    const updated = await updateProfile.mutateAsync({
      body_measurements: merged,
      expected_body_measurements_revision: base.body_measurements_revision,
      styling_profile: stylingProfile,
      expected_styling_profile_revision: base.styling_profile_revision,
    });
    if (mounted.current) {
      loadMeasurements(updated);
      setSaved(true);
    }
    return updated;
  }
  function handleError(err: unknown, fallback = "generic") {
    if (!mounted.current) return;
    if (
      err instanceof ApiError &&
      (err.data as { detail?: { code?: string } })?.detail?.code ===
        "body_measurements_conflict"
    ) {
      setConflict(true);
    }
    setError(friendlyError(err, fallback));
  }
  async function reloadMeasurements() {
    const latest = await refetchProfile();
    if (!mounted.current || !latest.data || latest.isError) return;
    loadMeasurements(latest.data);
    setSaved(false);
    setError("");
  }
  async function save(event: FormEvent) {
    event.preventDefault();
    setError("");
    if (!validateMeasurements()) return;
    try {
      await persistMeasurements();
    } catch (err) {
      handleError(err, "save");
    }
  }
  function openReport(id: string) {
    setSelectedId(id);
    router.replace("/dashboard/body-styling?report=" + encodeURIComponent(id), {
      scroll: false,
    });
  }
  async function generate() {
    if (generationRequest.current) return;
    setError("");
    if (!validateMeasurements()) return;
    if (!context.goals.length) {
      setError(t("goalRequired"));
      return;
    }
    if (!status.data?.available) {
      setError(t("error.ai_unavailable"));
      return;
    }
    setGenerating(true);
    const controller = new AbortController();
    generationRequest.current = controller;
    try {
      const updated = await persistMeasurements();
      if (!mounted.current || controller.signal.aborted) return;
      const report = await api.post<BodyStyleReport>(
        "/body-styling/recommendations",
        {
          ...context,
          body_measurements_revision: updated.body_measurements_revision,
          styling_profile_revision: updated.styling_profile_revision,
        },
        { signal: controller.signal },
      );
      if (!mounted.current || controller.signal.aborted) return;
      queryClient.setQueryData(queryKeys.bodyStyling.report(report.id), report);
      openReport(report.id);
      setOffset(0);
      await queryClient.invalidateQueries({ queryKey: queryKeys.bodyStyling.history.all });
    } catch (err) {
      if (!controller.signal.aborted) handleError(err);
    } finally {
      generationRequest.current = null;
      if (mounted.current) setGenerating(false);
    }
  }
  function factValue(fact: Fact) {
    if (fact.id in PROFILE_CATALOGS) {
      const group = PROFILE_CATALOGS[fact.id as keyof StylingProfile];
      return (Array.isArray(fact.value) ? fact.value : [String(fact.value)])
        .map((value) => catalogLabel(group, value, locale))
        .join(" · ");
    }
    if (fact.unit === "self_report" && fact.id !== "shoulder_type")
      return String(fact.value);
    return fact.id === "shoulder_type"
      ? t("shoulders." + fact.value)
      : `${fact.value}${fact.unit === "ratio" ? "" : ` ${fact.unit}`}`;
  }
  function evidence(ids: FactId[], facts: Fact[]) {
    return (
      <div className="mt-2 flex flex-wrap gap-1.5">
        {ids.map((id) => {
          const fact = facts.find((f) => f.id === id);
          return fact ? (
            <span
              key={id}
              className="rounded bg-muted px-2 py-1 text-[11px] text-muted-foreground"
            >
              {t("facts." + id)} {factValue(fact)}
            </span>
          ) : null;
        })}
      </div>
    );
  }
  const report = detail.data;
  const dateLabel = (value: string) =>
    new Date(value).toLocaleString(locale, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });

  return (
    <div
      className="mx-auto max-w-7xl space-y-7"
      data-testid="body-styling-page"
    >
      <header className="space-y-3 border-b pb-7">
        <p className="text-xs font-semibold tracking-[.18em] text-emerald-700 dark:text-emerald-400">
          {t("eyebrow")}
        </p>
        <h1 className="max-w-3xl text-3xl font-semibold leading-tight tracking-tight md:text-4xl">
          {t("heading")}
        </h1>
        <p className="max-w-2xl text-sm leading-7 text-muted-foreground">
          {t("intro")}
        </p>
      </header>

      {status.isError ? (
        <div
          role="alert"
          className="flex flex-wrap items-center gap-3 rounded-xl border p-4 text-sm"
        >
          <span>{t("statusError")}</span>
          <Button variant="outline" size="sm" onClick={() => status.refetch()}>
            {t("refresh")}
          </Button>
        </div>
      ) : status.data && !status.data.available ? (
        <div
          className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-amber-200 bg-amber-50/60 p-5 dark:border-amber-900 dark:bg-amber-950/20"
          data-testid="ai-unavailable"
        >
          <div className="max-w-3xl">
            <h2 className="text-sm font-semibold">{t("aiOffTitle")}</h2>
            <p className="mt-1 text-sm leading-6 text-muted-foreground">
              {t("aiOff")}
            </p>
          </div>
          <Button
            variant="outline"
            size="sm"
            disabled={status.isFetching}
            onClick={() => status.refetch()}
          >
            {t("refresh")}
          </Button>
        </div>
      ) : null}
      {(error || profileError) && (
        <div
          role="alert"
          className="rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive"
        >
          {error || t("error.load")}
        </div>
      )}
      {conflict && (
        <div role="alert" className="rounded-xl border p-4 text-sm">
          <p>{t("error.body_measurements_conflict")}</p>
          <Button
            variant="outline"
            className="mt-3"
            onClick={reloadMeasurements}
            disabled={generating || updateProfile.isPending}
          >
            {t("reloadMeasurements")}
          </Button>
        </div>
      )}

      <div className="grid items-start gap-6 xl:grid-cols-[340px_minmax(0,1fr)]">
        <div className="min-w-0 space-y-5">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-lg">
                <Ruler className="h-5 w-5" />
                {t("profileTitle")}
              </CardTitle>
              <CardDescription className="leading-6">
                {t("profileIntro")}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <form ref={formRef} onSubmit={save}>
                <fieldset
                  disabled={!profile || generating || updateProfile.isPending}
                  className="space-y-4"
                >
                  <div className="grid grid-cols-2 gap-3">
                    {MEASUREMENT_FIELDS.map((key, index) => (
                      <div key={key}>
                        <label
                          htmlFor={"body-" + key}
                          className="mb-1.5 block text-sm font-medium"
                        >
                          {t("fields." + key)}
                          {index < 4 && <span aria-hidden="true"> *</span>}
                        </label>
                        <div className="relative">
                          <Input
                            id={"body-" + key}
                            name={key}
                            type="number"
                            min="0.1"
                            max="1000"
                            step="0.1"
                            inputMode="decimal"
                            required={index < 4}
                            value={measurements[key] || ""}
                            onChange={(e) =>
                              changeMeasurement(key, e.target.value)
                            }
                            className="pr-9"
                          />
                          <span
                            aria-hidden="true"
                            className="absolute right-3 top-2.5 text-xs text-muted-foreground"
                          >
                            {key === "weight" ? "kg" : "cm"}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                  <div>
                    <label
                      className="mb-1.5 block text-sm font-medium"
                      htmlFor="body-shoulders"
                    >
                      {t("fields.shoulder_type")}
                    </label>
                    <select
                      id="body-shoulders"
                      value={measurements.shoulder_type || ""}
                      onChange={(e) =>
                        changeMeasurement("shoulder_type", e.target.value)
                      }
                      className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                    >
                      {["", "narrow", "balanced", "broad"].map((value) => (
                        <option key={value} value={value}>
                          {t("shoulders." + (value || "unknown"))}
                        </option>
                      ))}
                    </select>
                  </div>
                  <p className="text-xs leading-6 text-muted-foreground">
                    {t("measurementHelp")}
                  </p>
                  <StylingProfileEditor
                    value={stylingProfile}
                    onChange={(value) => {
                      dirty.current = true;
                      setStylingProfile(value);
                      setSaved(false);
                      setError("");
                    }}
                  />
                  <Button type="submit" variant="outline" className="w-full">
                    {updateProfile.isPending ? (
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    ) : saved ? (
                      <Check className="mr-2 h-4 w-4" />
                    ) : null}
                    {updateProfile.isPending
                      ? t("saving")
                      : saved
                        ? t("saved")
                        : t("save")}
                  </Button>
                </fieldset>
              </form>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">{t("requestTitle")}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-5">
              <fieldset disabled={generating} className="space-y-4">
                {(
                  [
                    ["occasion", occasionKeys, "occasions"],
                    ["style", styleKeys, "styles"],
                    ["season", seasonKeys, "seasons"],
                  ] as const
                ).map(([key, keys, prefix]) => (
                  <div key={key}>
                    <label
                      htmlFor={"style-" + key}
                      className="mb-1.5 block text-sm font-medium"
                    >
                      {t(key)}
                    </label>
                    <select
                      id={"style-" + key}
                      value={context[key]}
                      onChange={(e) =>
                        setContext((prev) => ({
                          ...prev,
                          [key]: e.target.value,
                        }))
                      }
                      className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                    >
                      {keys.map((value) => (
                        <option key={value} value={value}>
                          {t(prefix + "." + value)}
                        </option>
                      ))}
                    </select>
                  </div>
                ))}
                <div>
                  <p className="mb-2 text-sm font-medium">{t("goalsTitle")}</p>
                  <div className="flex flex-wrap gap-2">
                    {goalKeys.map((goal) => (
                      <button
                        key={goal}
                        type="button"
                        aria-pressed={context.goals.includes(goal)}
                        onClick={() => {
                          setContext((previous) => ({
                            ...previous,
                            goals: previous.goals.includes(goal)
                              ? previous.goals.filter((g) => g !== goal)
                              : [...previous.goals, goal],
                          }));
                          setError("");
                        }}
                        className={
                          "rounded-full border px-3 py-2 text-xs transition-colors " +
                          (context.goals.includes(goal)
                            ? "border-emerald-700 bg-emerald-700 text-white"
                            : "border-input hover:bg-accent")
                        }
                      >
                        {t("goals." + goal)}
                      </button>
                    ))}
                  </div>
                </div>
              </fieldset>
              <Button
                type="button"
                className="min-h-11 w-full bg-emerald-800 text-white hover:bg-emerald-900"
                disabled={
                  generating ||
                  updateProfile.isPending ||
                  !profile ||
                  !status.data?.available
                }
                onClick={generate}
              >
                {generating ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Sparkles className="mr-2 h-4 w-4" />
                )}
                {generating ? t("generating") : t("generate")}
              </Button>
              {status.data?.available && (
                <p className="flex items-center justify-center gap-1.5 text-xs text-muted-foreground">
                  <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />
                  {t("aiReady")}
                </p>
              )}
            </CardContent>
          </Card>
        </div>

        <div
          className="min-w-0 space-y-6"
          aria-live="polite"
          aria-busy={generating || detail.isFetching}
        >
          {generating && (
            <div
              role="status"
              className="flex items-start gap-3 rounded-xl border border-emerald-200 bg-emerald-50/40 p-5 dark:border-emerald-900 dark:bg-emerald-950/20"
            >
              <Loader2 className="mt-1 h-5 w-5 shrink-0 animate-spin text-emerald-700" />
              <p className="text-sm leading-6">{t("generatingNote")}</p>
            </div>
          )}
          {detail.isFetching && (
            <p className="text-sm text-muted-foreground">
              {t("reportLoading")}
            </p>
          )}
          {detail.isError && (
            <p
              role="alert"
              className="rounded-xl border p-5 text-sm text-destructive"
            >
              {t("error.load")}
            </p>
          )}
          {!selectedId && !generating && (
            <div className="rounded-2xl border border-dashed bg-muted/20 px-6 py-12 text-center md:px-12">
              <div className="mx-auto mb-6 flex h-14 w-14 items-center justify-center rounded-full bg-emerald-100 text-emerald-800">
                <Sparkles className="h-6 w-6" />
              </div>
              <h2 className="text-xl font-semibold">{t("emptyTitle")}</h2>
              <p className="mx-auto mt-3 max-w-md text-sm leading-7 text-muted-foreground">
                {t("emptyIntro")}
              </p>
              <ol className="mx-auto mt-8 max-w-sm space-y-3 text-left">
                {[
                  t("emptySteps.measure"),
                  t("emptySteps.context"),
                  t("emptySteps.looks"),
                ].map((step, index) => (
                  <li key={step} className="flex items-center gap-3 text-sm">
                    <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border text-xs">
                      {index + 1}
                    </span>
                    {step}
                  </li>
                ))}
              </ol>
            </div>
          )}
          {report && (
            <section className="space-y-6" data-testid="body-style-report">
              <Card>
                <CardHeader>
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <CardTitle className="text-xl">{t("analysis")}</CardTitle>
                    <span className="text-xs text-muted-foreground">
                      {dateLabel(report.created_at)}
                    </span>
                  </div>
                  <CardDescription className="pt-2 text-base leading-7 text-foreground">
                    {report.result.summary}
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-5">
                  <div>
                    <h3 className="mb-2 text-xs font-semibold text-muted-foreground">
                      {t("factsTitle")}
                    </h3>
                    <div className="flex flex-wrap gap-2">
                      {report.facts.map((fact) => (
                        <span
                          key={fact.id}
                          className="rounded-md border px-2.5 py-1.5 text-xs"
                        >
                          <span className="text-muted-foreground">
                            {t("facts." + fact.id)}{" "}
                          </span>
                          <strong className="font-medium">
                            {factValue(fact)}
                          </strong>
                        </span>
                      ))}
                    </div>
                  </div>
                  <div className="space-y-4">
                    {report.result.observations.map((observation, index) => (
                      <div key={index}>
                        <p className="text-sm leading-7">{observation.text}</p>
                        {evidence(observation.evidence, report.facts)}
                      </div>
                    ))}
                  </div>
                  {!!report.result.unknowns.length && (
                    <div className="rounded-lg bg-muted/50 p-4">
                      <h3 className="mb-2 text-sm font-medium">
                        {t("unknowns")}
                      </h3>
                      <ul className="list-inside list-disc space-y-1 text-xs leading-6 text-muted-foreground">
                        {report.result.unknowns.map((text, index) => (
                          <li key={index}>{text}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  <p className="text-xs leading-5 text-muted-foreground">
                    {t("snapshot")}
                  </p>
                </CardContent>
              </Card>
              {(report.result.color_guidance ||
                report.result.fabric_guidance) && (
                <div
                  className="grid gap-3 sm:grid-cols-2"
                  data-testid="personal-style-guidance"
                >
                  {(["color_guidance", "fabric_guidance"] as const).map(
                    (key) =>
                      report.result[key] ? (
                        <div key={key} className="rounded-xl border p-4">
                          <h2 className="mb-2 text-sm font-semibold text-emerald-800 dark:text-emerald-300">
                            {t(key)}
                          </h2>
                          <p className="text-sm leading-7">
                            {report.result[key]!.text}
                          </p>
                          {evidence(report.result[key]!.evidence, report.facts)}
                        </div>
                      ) : null,
                  )}
                </div>
              )}
              {!report.input_snapshot.contract_version && (
                <p className="text-xs leading-6 text-muted-foreground">
                  {t("legacyReport")}
                </p>
              )}
              <div>
                <h2 className="mb-3 text-lg font-semibold">{t("fitAdvice")}</h2>
                <div className="grid gap-3 sm:grid-cols-2">
                  {report.result.fit_advice.map((advice) => (
                    <div key={advice.area} className="rounded-xl border p-4">
                      <h3 className="mb-2 text-sm font-semibold text-emerald-800 dark:text-emerald-300">
                        {t("areas." + advice.area)}
                      </h3>
                      <p className="text-sm leading-6 text-muted-foreground">
                        {advice.text}
                      </p>
                      {evidence(advice.evidence, report.facts)}
                    </div>
                  ))}
                </div>
              </div>
              <div>
                <h2 className="mb-1 text-lg font-semibold">
                  {t("looksTitle")}
                </h2>
                <p className="mb-4 text-xs leading-6 text-muted-foreground">
                  {t("schematicNote")}
                </p>
                <div className="grid items-start gap-4 min-[1500px]:grid-cols-3">
                  {report.result.outfits.map((outfit, index) => (
                    <Card
                      key={index}
                      className="overflow-hidden"
                      data-testid="body-outfit-card"
                    >
                      <CardHeader className="pb-3">
                        <p className="text-[11px] font-semibold tracking-widest text-emerald-700 dark:text-emerald-400">
                          {t("lookNumber", { number: index + 1 })}
                        </p>
                        <CardTitle className="text-lg">
                          {outfit.title}
                        </CardTitle>
                      </CardHeader>
                      <CardContent className="space-y-4">
                        <OutfitIllustration outfit={outfit} />
                        {outfit.color_plan && (
                          <div
                            className="space-y-2"
                            data-testid="outfit-color-plan"
                          >
                            <p className="text-xs font-semibold">
                              {catalogLabel(
                                "color_strategy",
                                outfit.color_plan.strategy,
                                locale,
                              )}
                            </p>
                            <div
                              className="flex h-4 overflow-hidden rounded-full border"
                              aria-hidden="true"
                            >
                              {outfit.garments.map((garment) => (
                                <span
                                  key={garment.slot}
                                  className="flex-1"
                                  style={{ backgroundColor: garment.color }}
                                />
                              ))}
                            </div>
                            <p className="text-xs leading-5 text-muted-foreground">
                              {outfit.garments
                                .map(
                                  (garment) =>
                                    `${t("slots." + garment.slot)} · ${garment.color_name}`,
                                )
                                .join(" / ")}
                            </p>
                          </div>
                        )}
                        <ul className="space-y-3">
                          {outfit.garments.map((garment) => (
                            <li key={garment.slot} className="flex gap-3">
                              <span
                                aria-hidden="true"
                                className="mt-1 h-4 w-4 shrink-0 rounded-full border border-black/15"
                                style={{ backgroundColor: garment.color }}
                              />
                              <div className="min-w-0">
                                <p className="text-sm font-medium">
                                  {garment.color_name} ·{" "}
                                  {t("kind." + garment.kind)}
                                </p>
                                <p className="mt-0.5 text-xs leading-5 text-muted-foreground">
                                  {[
                                    t("fit." + garment.fit),
                                    t(
                                      (garment.slot === "bottom" &&
                                      garment.kind !== "shorts"
                                        ? "trouserLength."
                                        : "length.") + garment.length,
                                    ),
                                    garment.rise
                                      ? t("rise." + garment.rise)
                                      : null,
                                    garment.material,
                                  ]
                                    .filter(Boolean)
                                    .join(" · ")}
                                </p>
                                <p className="mt-1 text-xs leading-6">
                                  {garment.description}
                                </p>
                                {garment.fabric_summary && (
                                  <p
                                    className="mt-2 rounded-md bg-muted/60 px-2 py-1.5 text-xs leading-6"
                                    data-testid="garment-fabric"
                                  >
                                    {garment.fabric_summary}
                                  </p>
                                )}
                                {garment.fabric_reason && (
                                  <p className="mt-1 text-xs leading-6 text-muted-foreground">
                                    {garment.fabric_reason}
                                  </p>
                                )}
                              </div>
                            </li>
                          ))}
                        </ul>
                        <div className="border-t pt-4">
                          <h3 className="mb-1 text-xs font-semibold">
                            {t("why")}
                          </h3>
                          <p className="text-sm leading-6">
                            {outfit.body_reason}
                          </p>
                          {evidence(outfit.evidence, report.facts)}
                        </div>
                        {(["color_reason", "fabric_reason"] as const).map(
                          (key) =>
                            outfit[key] ? (
                              <div key={key} className="border-t pt-3">
                                <h3 className="mb-1 text-xs font-semibold">
                                  {t(key)}
                                </h3>
                                <p className="text-sm leading-7">
                                  {outfit[key]!.text}
                                </p>
                                {evidence(outfit[key]!.evidence, report.facts)}
                              </div>
                            ) : null,
                        )}
                        <div className="rounded-lg bg-muted/50 p-3">
                          <h3 className="mb-1 text-xs font-semibold">
                            {t("tip")}
                          </h3>
                          <p className="text-xs leading-6 text-muted-foreground">
                            {outfit.styling_tip}
                          </p>
                        </div>
                        <OutfitFeedback report={report} index={index} />
                      </CardContent>
                    </Card>
                  ))}
                </div>
              </div>
            </section>
          )}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-lg">
                <Clock3 className="h-4 w-4" />
                {t("historyTitle")}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {history.isLoading ? (
                <p className="text-sm text-muted-foreground">
                  {t("historyLoading")}
                </p>
              ) : history.isError ? (
                <p role="alert" className="text-sm text-destructive">
                  {t("error.history")}
                </p>
              ) : !history.data?.items.length ? (
                <p className="text-sm leading-6 text-muted-foreground">
                  {t("historyEmpty")}
                </p>
              ) : (
                history.data.items.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => openReport(item.id)}
                    className={
                      "flex w-full items-center gap-3 rounded-xl border p-4 text-left transition-colors hover:bg-accent " +
                      (selectedId === item.id
                        ? "border-emerald-600 bg-emerald-50/40 dark:bg-emerald-950/20"
                        : "")
                    }
                  >
                    <div className="min-w-0 flex-1">
                      <p className="text-xs text-muted-foreground">
                        {dateLabel(item.created_at)} ·{" "}
                        {t("styles." + item.context.style)} ·{" "}
                        {t("occasions." + item.context.occasion)}
                      </p>
                      <p className="mt-1 line-clamp-2 text-sm leading-6">
                        {item.summary}
                      </p>
                    </div>
                    <span className="sr-only">{t("historyView")}</span>
                    <ArrowRight className="h-4 w-4 shrink-0" />
                  </button>
                ))
              )}
              {!!history.data?.total && (
                <div className="flex flex-wrap items-center justify-between gap-2 pt-2 text-xs text-muted-foreground">
                  <span>
                    {t("historyPage", {
                      start: offset + 1,
                      end: Math.min(offset + 10, history.data.total),
                      total: history.data.total,
                    })}
                  </span>
                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={offset === 0}
                      onClick={() =>
                        setOffset((previous) => Math.max(0, previous - 10))
                      }
                    >
                      {t("previous")}
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={offset + 10 >= history.data.total}
                      onClick={() => setOffset((previous) => previous + 10)}
                    >
                      {t("next")}
                    </Button>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
