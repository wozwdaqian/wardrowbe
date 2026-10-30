"use client";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { api } from "@/lib/api";
import {
  BodyStyleReport,
  OutfitFeedback as Feedback,
  ReportFeedback,
} from "@/lib/body-styling";

export function OutfitFeedback({
  report,
  index,
}: {
  report: BodyStyleReport;
  index: number;
}) {
  const t = useTranslations("bodyStyling");
  const queryClient = useQueryClient();
  const current = report.feedback?.outfits.find(
    (item) => item.outfit_index === index,
  );
  const save = useMutation({
    meta: { toastsOwnErrors: true },
    mutationFn: (value: Feedback) =>
      api.patch<ReportFeedback>(
        `/body-styling/recommendations/${report.id}/feedback`,
        value,
      ),
    onSuccess: (feedback) =>
      queryClient.setQueryData<BodyStyleReport>(
        ["body-style-report", report.id],
        (old) => (old ? { ...old, feedback } : old),
      ),
  });
  return (
    <div className="space-y-2 border-t pt-4" data-testid="outfit-feedback">
      <h3 className="text-xs font-semibold">{t("feedback.title")}</h3>
      <p className="text-xs leading-5 text-muted-foreground">
        {t("feedback.intro")}
      </p>
      {(["overall", "colors", "fabrics"] as const).map((field) => (
        <div
          key={field}
          className="flex flex-wrap items-center justify-between gap-2"
        >
          <span className="text-xs">{t("feedback." + field)}</span>
          <div className="flex gap-1">
            {(["like", "dislike"] as const).map((rating) => (
              <button
                type="button"
                key={rating}
                disabled={save.isPending}
                aria-label={
                  t("feedback." + field) + " · " + t("feedback." + rating)
                }
                aria-pressed={current?.[field] === rating}
                onClick={() =>
                  save.mutate({
                    outfit_index: index,
                    overall: current?.overall || null,
                    colors: current?.colors || null,
                    fabrics: current?.fabrics || null,
                    [field]: current?.[field] === rating ? null : rating,
                  })
                }
                className={`rounded-md border px-2.5 py-1.5 text-xs ${current?.[field] === rating ? "border-emerald-700 bg-emerald-50 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-100" : "hover:bg-muted"}`}
              >
                {t("feedback." + rating)}
              </button>
            ))}
          </div>
        </div>
      ))}
      {save.isError && (
        <p role="alert" className="text-xs text-destructive">
          {t("feedback.error")}
        </p>
      )}
      {save.isSuccess && (
        <p role="status" className="text-xs text-muted-foreground">
          {t("feedback.saved")}
        </p>
      )}
    </div>
  );
}
