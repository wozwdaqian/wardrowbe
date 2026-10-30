import { Garment } from "@/lib/body-styling";

// Stylized local marks communicate texture; they do not simulate an actual fabric.
export function FabricPattern({
  garment,
  id,
}: {
  garment: Garment;
  id: string;
}) {
  if (!garment.fabric) return null;
  const construction = garment.fabric.construction;
  const diagonal = ["twill", "denim_weave"].includes(construction);
  const knitted = ["knit", "jersey", "fleece"].includes(construction);
  return (
    <pattern id={id} width="8" height="8" patternUnits="userSpaceOnUse">
      <rect width="8" height="8" fill={garment.color} />
      {diagonal ? (
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
      {garment.fabric.sheen !== "matte" && (
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
