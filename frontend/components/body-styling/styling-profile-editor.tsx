"use client";

import { useLocale, useTranslations } from "next-intl";
import {
  catalogLabel,
  PROFILE_CATALOGS,
  STYLING_CATALOG,
  StylingProfile,
} from "@/lib/body-styling";

type Props = {
  value: StylingProfile;
  onChange: (value: StylingProfile) => void;
};
export function StylingProfileEditor({ value, onChange }: Props) {
  const t = useTranslations("bodyStyling");
  const locale = useLocale();
  function toggle(
    field:
      | "preferred_color_families"
      | "avoided_color_families"
      | "avoided_materials"
      | "fabric_preferences"
      | "fit_issues",
    option: string,
  ) {
    const selected: string[] = value[field] || [];
    const removing = selected.includes(option);
    const limit =
      field === "avoided_materials"
        ? 10
        : field === "fabric_preferences"
          ? 6
          : 8;
    if (!removing && selected.length >= limit) return;
    const next = {
      ...value,
      [field]: removing
        ? selected.filter((item) => item !== option)
        : [...selected, option],
    };
    // One tap moves a family from the opposite group; a contradictory preference cannot be saved.
    if (
      !removing &&
      (field === "preferred_color_families" ||
        field === "avoided_color_families")
    ) {
      const opposite =
        field === "preferred_color_families"
          ? "avoided_color_families"
          : "preferred_color_families";
      next[opposite] = (value[opposite] || []).filter(
        (item) => item !== option,
      );
    }
    onChange(next as StylingProfile);
  }
  function choices(
    field:
      | "preferred_color_families"
      | "avoided_color_families"
      | "avoided_materials"
      | "fabric_preferences"
      | "fit_issues",
  ) {
    return (
      <div className="space-y-2">
        <p className="text-sm font-medium" id={"label-" + field}>
          {t("personal." + field)}
        </p>
        <div
          className="flex flex-wrap gap-1.5"
          role="group"
          aria-labelledby={"label-" + field}
        >
          {Object.keys(STYLING_CATALOG[PROFILE_CATALOGS[field]]).map(
            (option) => (
              <button
                type="button"
                key={option}
                aria-pressed={
                  (value[field] as string[] | undefined)?.includes(option) ||
                  false
                }
                data-testid={`${field}-${option}`}
                onClick={() => toggle(field, option)}
                className={`rounded-full border px-2.5 py-1.5 text-xs transition-colors ${((value[field] || []) as string[]).includes(option) ? "border-emerald-800 bg-emerald-800 text-white dark:border-emerald-500 dark:bg-emerald-900" : "bg-background hover:bg-muted"}`}
              >
                {catalogLabel(PROFILE_CATALOGS[field], option, locale)}
              </button>
            ),
          )}
        </div>
      </div>
    );
  }
  return (
    <div
      className="space-y-3 border-t pt-4"
      data-testid="styling-profile-editor"
    >
      <div>
        <h3 className="font-semibold">{t("personal.title")}</h3>
        <p className="mt-1 text-xs leading-6 text-muted-foreground">
          {t("personal.intro")}
        </p>
      </div>
      <details className="rounded-lg border p-3" open>
        <summary className="cursor-pointer text-sm font-medium">
          {t("personal.appearance")}
        </summary>
        <p className="mt-2 text-xs leading-6 text-muted-foreground">
          {t("personal.skinHelp")}
        </p>
        <div className="mt-3 grid grid-cols-2 gap-3">
          {(
            [
              "skin_depth",
              "undertone",
              "hair_color",
              "eye_color",
              "contrast_preference",
            ] as const
          ).map((field) => (
            <div key={field}>
              <label
                htmlFor={"styling-" + field}
                className="mb-1.5 block text-xs font-medium"
              >
                {t("personal." + field)}
              </label>
              <select
                id={"styling-" + field}
                value={value[field] || ""}
                onChange={(event) =>
                  onChange({ ...value, [field]: event.target.value || null })
                }
                className="h-10 w-full rounded-md border border-input bg-background px-2 text-xs"
              >
                <option value="">{t("personal.unknown")}</option>
                {Object.keys(STYLING_CATALOG[field]).map((option) => (
                  <option key={option} value={option}>
                    {catalogLabel(field, option, locale)}
                  </option>
                ))}
              </select>
            </div>
          ))}
        </div>
      </details>
      <details className="rounded-lg border p-3">
        <summary className="cursor-pointer text-sm font-medium">
          {t("personal.colors")}
        </summary>
        <div className="mt-3 space-y-4">
          {choices("preferred_color_families")}
          {choices("avoided_color_families")}
          <p className="text-xs leading-6 text-muted-foreground">
            {t("personal.colorHelp")}
          </p>
        </div>
      </details>
      <details className="rounded-lg border p-3">
        <summary className="cursor-pointer text-sm font-medium">
          {t("personal.fabrics")}
        </summary>
        <div className="mt-3 space-y-4">
          {choices("fabric_preferences")}
          {choices("avoided_materials")}
          <p className="text-xs leading-6 text-muted-foreground">
            {t("personal.fabricHelp")}
          </p>
        </div>
      </details>
      <details className="rounded-lg border p-3">
        <summary className="cursor-pointer text-sm font-medium">
          {t("personal.fit_issues")}
        </summary>
        <div className="mt-3">{choices("fit_issues")}</div>
      </details>
    </div>
  );
}
