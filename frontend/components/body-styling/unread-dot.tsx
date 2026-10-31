"use client";

import { useTranslations } from "next-intl";
import { useBodyStyleUnread } from "@/lib/hooks/use-body-styling";
import { cn } from "@/lib/utils";

export function BodyStyleUnreadDot({ className }: { className?: string }) {
  const t = useTranslations("nav");
  const { data } = useBodyStyleUnread();
  if (!data?.unread) return null;
  return (
    <span
      className={cn("h-2 w-2 shrink-0 rounded-full bg-red-500", className)}
      role="status"
      aria-label={t("bodyStylingUnread", { count: data.unread })}
      data-testid="body-style-unread"
    />
  );
}
