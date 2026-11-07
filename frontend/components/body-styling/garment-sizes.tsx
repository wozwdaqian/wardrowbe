"use client";
import { useTranslations } from "next-intl";
import type { Garment } from "@/lib/body-styling";
import { garmentSizes, missingForSizes } from "@/lib/size-guide";

// Suggested flat measurements for one garment, to compare with a product's size chart.
export function GarmentSizes({
  garment,
  measurements,
}: {
  garment: Garment;
  measurements: Record<string, number | string>;
}) {
  const t = useTranslations("bodyStyling.sizes");
  const rows = garmentSizes(garment, measurements);
  if (!rows.length) return null;
  const missing = missingForSizes(garment, measurements);
  return (
    <p
      className="mt-1 text-xs leading-6 text-muted-foreground"
      data-testid="garment-sizes"
    >
      <span className="font-medium text-foreground">{t("label")}</span>{" "}
      {rows
        .map((r) =>
          t("row", { name: t(`keys.${r.key}`), min: r.min, max: r.max }),
        )
        .join(" · ")}
      {missing.length > 0 && (
        <span className="block">
          {t("missing", {
            fields: missing.map((m) => t(`fields.${m}`)).join(t("joiner")),
          })}
        </span>
      )}
    </p>
  );
}
