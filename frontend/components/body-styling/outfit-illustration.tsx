"use client";
import { useId } from "react";
import { useTranslations } from "next-intl";
import { BodyOutfit, Garment, silhouetteMetrics } from "@/lib/body-styling";
import { FabricPattern, hasSurface } from "./fabric-pattern";

function Top({
  g,
  x,
  y,
  width,
  height,
  open = false,
  fill,
}: {
  g: Garment;
  x: number;
  y: number;
  width: number;
  height: number;
  open?: boolean;
  fill?: string;
}) {
  const shortSleeve = ["tshirt", "polo"].includes(g.kind);
  const sleeveless = g.kind === "vest";
  return (
    <g
      transform={`translate(${x - width / 2} ${y}) scale(${width / 100} ${height / 110})`}
      fill={fill || g.color}
      stroke="#283831"
      strokeOpacity=".33"
      strokeWidth="1.3"
      strokeLinejoin="round"
    >
      <path
        d={
          sleeveless
            ? "M33 9 24 18 27 108 73 108 76 18 67 9 50 45Z"
            : shortSleeve
              ? "M30 7 18 14 1 37 18 50 27 38 27 108 73 108 73 38 82 50 99 37 82 14 70 7Q50 19 30 7Z"
              : "M30 7 16 15 0 83 17 89 28 41 26 108 74 108 72 41 83 89 100 83 84 15 70 7Q50 19 30 7Z"
        }
      />
      {g.kind === "turtleneck" && <path d="M38 -4H62V12Q50 18 38 12Z" />}
      {g.kind === "down_jacket" && (
        <path
          d="M27 35H73M27 55H73M27 75H73M27 95H73M4 50 22 52M96 50 78 52"
          fill="none"
          strokeOpacity=".3"
        />
      )}
      {g.kind === "trench" && (
        <path d="M24 62H76" fill="none" strokeWidth="4" strokeOpacity=".45" />
      )}
      {open ? (
        <>
          <path
            d="M40 12 43 108H57L60 12 50 23Z"
            fill="#f4f2ec"
            stroke="none"
          />
          <path
            d="M32 9 41 37 49 25 40 12M68 9 59 37 51 25 60 12"
            fill="none"
          />
        </>
      ) : sleeveless ? (
        <path d="M50 45V105M47 60H53M47 78H53" fill="none" />
      ) : (
        <>
          {g.kind !== "turtleneck" && (
            <path d="M35 9Q50 30 65 9" fill="none" strokeWidth="2" />
          )}
          {["shirt", "polo"].includes(g.kind) && !sleeveless && (
            <>
              <path d="M33 8 39 27 50 18 61 27 67 8M50 20V105" fill="none" />
              <circle cx="53" cy="39" r="1" />
              <circle cx="53" cy="59" r="1" />
              <circle cx="53" cy="79" r="1" />
            </>
          )}
          {g.kind === "shirt" && <path d="M58 36H68V51H58Z" fill="none" />}
        </>
      )}
      <path d="M29 103H71" fill="none" strokeOpacity=".18" />
    </g>
  );
}
const MID_LAYERS: Garment["kind"][] = [
  "knit",
  "sweatshirt",
  "cardigan",
  "vest",
];
const OPEN_LAYERS: Garment["kind"][] = [
  "blazer",
  "suit_jacket",
  "jacket",
  "overshirt",
  "coat",
  "trench",
];
const SIDE_SPOTS = [
  [266, 245],
  [54, 245],
];

function Accessory({
  g,
  fill,
  x,
  y,
}: {
  g: Garment;
  fill: string;
  x: number;
  y: number;
}) {
  return (
    <g
      transform={`translate(${x} ${y})`}
      stroke="#283831"
      strokeWidth="1.2"
      strokeOpacity=".4"
      fill={fill}
    >
      {g.kind === "bag" ? (
        <>
          <rect x="-19" y="0" width="38" height="43" rx="5" />
          <path d="M-11 0V-8Q0-22 11-8V0" fill="none" />
        </>
      ) : g.kind === "cap" ? (
        <path d="M-20 0Q-20-24 0-24T20 0L30 8H-20Z" />
      ) : g.kind === "scarf" ? (
        <>
          <path d="M-13-15H12L6 10 18 41H4L-7 16-15 40H-26L-9 6Z" />
          <path d="M-8-14 0 8" fill="none" />
        </>
      ) : g.kind === "watch" ? (
        <>
          <rect x="-5" y="-14" width="10" height="38" rx="3" />
          <circle cx="0" cy="5" r="9" fill="#f4f2ec" />
          <path d="M0 5V0M0 5H4" fill="none" />
        </>
      ) : g.kind === "glasses" ? (
        <>
          <circle
            cx="-12"
            cy="0"
            r="9"
            fill="none"
            strokeWidth="2.5"
            stroke={g.color}
            strokeOpacity="1"
          />
          <circle
            cx="12"
            cy="0"
            r="9"
            fill="none"
            strokeWidth="2.5"
            stroke={g.color}
            strokeOpacity="1"
          />
          <path
            d="M-3 0H3"
            fill="none"
            strokeWidth="2.5"
            stroke={g.color}
            strokeOpacity="1"
          />
        </>
      ) : (
        <>
          <rect x="-23" y="0" width="46" height="10" rx="3" />
          <rect x="-3" y="-2" width="12" height="14" fill="none" />
        </>
      )}
    </g>
  );
}

export function OutfitIllustration({ outfit }: { outfit: BodyOutfit }) {
  const t = useTranslations("bodyStyling");
  const patternId = "fabric-" + useId().replace(/:/g, "");
  const fill = (garment: Garment) => {
    const index = outfit.garments.indexOf(garment);
    return hasSurface(garment) ? `url(#${patternId}-${index})` : garment.color;
  };
  const tops = outfit.garments.filter((g) => g.slot === "top");
  // The base layer is drawn first; a knit, sweatshirt, cardigan or vest goes over it.
  const top = tops.find((g) => !MID_LAYERS.includes(g.kind)) || tops[0];
  const mid = tops.find((g) => g !== top);
  const bottom = outfit.garments.find((g) => g.slot === "bottom")!;
  const shoes = outfit.garments.find((g) => g.slot === "shoes")!;
  const outer = outfit.garments.find((g) => g.slot === "outerwear");
  const accessories = outfit.garments.filter((g) => g.slot === "accessory");
  const tie = accessories.find((g) => g.kind === "tie");
  const side = accessories.filter((g) => g !== tie);
  const tm = silhouetteMetrics(top),
    bm = silhouetteMetrics(bottom);
  const legWidth = bm.width * 0.79,
    shoeY = bm.bottomY + bm.legHeight + 10;
  const longOuter = outer && ["coat", "trench"].includes(outer.kind);
  return (
    <svg
      role="img"
      aria-label={`${outfit.title} · ${t("schematic")}`}
      viewBox="0 0 320 400"
      className="w-full max-h-80"
      data-testid="outfit-illustration"
    >
      <defs>
        {outfit.garments.map((garment, index) => (
          <FabricPattern
            key={index}
            garment={garment}
            id={`${patternId}-${index}`}
          />
        ))}
      </defs>
      <rect width="320" height="400" rx="18" fill="#f5f3ed" />
      <circle cx="160" cy="193" r="137" fill="#ebece2" />
      <ellipse cx="160" cy="373" rx="85" ry="9" fill="#273b31" opacity=".055" />
      <g
        transform={`translate(${160 - legWidth / 2} ${bm.bottomY}) scale(${legWidth / 100} ${bm.legHeight / 200})`}
        fill={fill(bottom)}
        stroke="#283831"
        strokeOpacity=".35"
        strokeWidth="1.5"
      >
        <path d="M6 0H94L100 197H60L50 51 40 197H0Z" />
        <path
          d="M7 10H93M50 1V38M8 21Q28 22 30 11M92 21Q72 22 70 11"
          fill="none"
        />
        <path d="M5 190H39M61 190H96" fill="none" />
      </g>
      {outer && (
        <Top
          g={outer}
          fill={fill(outer)}
          x={160}
          y={40}
          width={
            silhouetteMetrics(outer).width +
            (outer.kind === "down_jacket" ? 37 : 27)
          }
          height={
            longOuter
              ? silhouetteMetrics(outer).topHeight + 60
              : silhouetteMetrics(outer).topHeight + 20
          }
          open={OPEN_LAYERS.includes(outer.kind)}
        />
      )}
      <Top
        g={top}
        x={160}
        y={49}
        width={tm.width}
        height={tm.topHeight}
        fill={fill(top)}
      />
      {tie && (
        <path
          d="M156 66H164L167 74 163 130 160 136 157 130 153 74Z"
          fill={fill(tie)}
          stroke="#283831"
          strokeOpacity=".4"
        />
      )}
      {mid && (
        <Top
          g={mid}
          x={160}
          y={51}
          width={silhouetteMetrics(mid).width + 6}
          height={silhouetteMetrics(mid).topHeight - 4}
          fill={fill(mid)}
          open={mid.kind === "cardigan"}
        />
      )}
      {outer && OPEN_LAYERS.includes(outer.kind) && (
        <g fill="none" stroke={outer.color} strokeWidth="8">
          <path d="M119 68 122 146M201 68 198 146" />
        </g>
      )}
      {[-1, 1].map((side) => (
        <g
          key={side}
          transform={`translate(${160 + side * 26} ${shoeY}) scale(${side} 1)`}
          fill={fill(shoes)}
          stroke="#283831"
          strokeWidth="1"
          strokeOpacity=".4"
        >
          {shoes.kind === "boots" ? (
            <path d="M-13-14H9V0L22 8Q29 20 5 20H-15Z" />
          ) : shoes.kind === "sandals" ? (
            <>
              <path d="M-17 16H24Q27 20 20 21H-15Z" />
              <path
                d="M-8 16Q0 2 10 16M4 16 12 6"
                fill="none"
                strokeWidth="3"
                stroke={shoes.color}
                strokeOpacity="1"
              />
            </>
          ) : (
            <path d="M-15 0Q-5 5 8 0L23 11Q28 22-11 20L-17 15Z" />
          )}
          <path d="M-15 15H23" fill="none" />
          {shoes.kind === "sneakers" && (
            <path d="M-3 4 9 8M-7 8 5 12" fill="none" />
          )}
          {shoes.kind === "oxfords" && <path d="M2 2 6 9" fill="none" />}
        </g>
      ))}
      {side.map((accessory, index) => (
        <Accessory
          key={index}
          g={accessory}
          fill={fill(accessory)}
          x={SIDE_SPOTS[index][0]}
          y={SIDE_SPOTS[index][1]}
        />
      ))}
    </svg>
  );
}
