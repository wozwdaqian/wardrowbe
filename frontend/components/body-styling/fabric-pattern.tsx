import { Garment } from "@/lib/body-styling";

// Stylized local marks communicate texture and print; they do not simulate an actual fabric.
function PrintMarks({ pattern }: { pattern: Garment["pattern"] }) {
  switch (pattern) {
    case "stripe":
      return (
        <path
          d="M2 0V8M6 0V8"
          stroke="white"
          strokeOpacity=".45"
          strokeWidth="1"
        />
      );
    case "check":
      return (
        <path
          d="M0 4H8M4 0V8"
          stroke="white"
          strokeOpacity=".4"
          strokeWidth="1.2"
        />
      );
    case "herringbone":
      return (
        <path
          d="M0 0 2 2 0 4 2 6 0 8M4 0 6 2 4 4 6 6 4 8"
          fill="none"
          stroke="white"
          strokeOpacity=".3"
          strokeWidth=".8"
        />
      );
    case "dot":
      return (
        <g fill="white" fillOpacity=".5">
          <circle cx="2" cy="2" r="1" />
          <circle cx="6" cy="6" r="1" />
        </g>
      );
    default:
      return null;
  }
}

export function hasSurface(garment: Garment) {
  return Boolean(
    garment.fabric || (garment.pattern && garment.pattern !== "solid"),
  );
}

export function FabricPattern({
  garment,
  id,
}: {
  garment: Garment;
  id: string;
}) {
  if (!hasSurface(garment)) return null;
  const construction = garment.fabric?.construction;
  const diagonal = ["twill", "denim_weave"].includes(construction || "");
  const knitted = ["knit", "jersey", "fleece"].includes(construction || "");
  return (
    <pattern id={id} width="8" height="8" patternUnits="userSpaceOnUse">
      <rect width="8" height="8" fill={garment.color} />
      {!construction ? null : diagonal ? (
        <path
          d="M-2 2 2-2M0 8 8 0M6 10 10 6"
          stroke="white"
          strokeOpacity=".16"
          strokeWidth="1"
        />
      ) : knitted ? (
        <path
          d="M0 1 2 4 4 1M4 5 6 8 8 5"
          fill="none"
          stroke="white"
          strokeOpacity=".14"
          strokeWidth=".7"
        />
      ) : construction === "mesh" || construction === "pique" ? (
        <g fill="black" fillOpacity=".13">
          <circle cx="2" cy="2" r=".7" />
          <circle cx="6" cy="6" r=".7" />
        </g>
      ) : (
        <path
          d="M0 2H8M2 0V8"
          stroke="white"
          strokeOpacity=".12"
          strokeWidth=".6"
        />
      )}
      <PrintMarks pattern={garment.pattern} />
      {garment.fabric && garment.fabric.sheen !== "matte" && (
        <path
          d="M0 0H8"
          stroke="white"
          strokeWidth={garment.fabric.sheen === "glossy" ? "2" : "1"}
          strokeOpacity=".16"
        />
      )}
    </pattern>
  );
}
