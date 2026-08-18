import { ImageResponse } from "next/og";
import {
  PRAVIAR_MARK_BAND_PATHS,
  PRAVIAR_MARK_INK_PATH,
  PRAVIAR_MARK_ON_LIGHT_FILLS,
  PRAVIAR_MARK_ON_LIGHT_OUTLINE,
  PRAVIAR_MARK_TILE_PATH,
  PRAVIAR_MARK_VIEWBOX,
} from "@/components/icons/praviar-mark";
import { BRAND } from "@/marketing/content";

export const size = {
  width: 1200,
  height: 630,
};

export const contentType = "image/png";

const OG_SOFT_MINT = "#D7ECE5";

function OgMark() {
  return (
    <svg
      width="164"
      height="164"
      viewBox={PRAVIAR_MARK_VIEWBOX}
      aria-hidden="true"
    >
      <path
        d={PRAVIAR_MARK_TILE_PATH}
        fill={PRAVIAR_MARK_ON_LIGHT_FILLS.paper}
        stroke={PRAVIAR_MARK_ON_LIGHT_OUTLINE}
        strokeWidth={4}
      />
      <path d={PRAVIAR_MARK_INK_PATH} fill={PRAVIAR_MARK_ON_LIGHT_FILLS.ink} />
      <path
        d={PRAVIAR_MARK_BAND_PATHS[0]}
        fill={PRAVIAR_MARK_ON_LIGHT_FILLS.mint}
      />
      <path
        d={PRAVIAR_MARK_BAND_PATHS[1]}
        fill={PRAVIAR_MARK_ON_LIGHT_FILLS.teal}
      />
      <path
        d={PRAVIAR_MARK_BAND_PATHS[2]}
        fill={PRAVIAR_MARK_ON_LIGHT_FILLS.copper}
      />
      <path
        d={PRAVIAR_MARK_BAND_PATHS[3]}
        fill={PRAVIAR_MARK_ON_LIGHT_FILLS.softMint}
      />
    </svg>
  );
}

export default function Image() {
  return new ImageResponse(
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        background: "#F6F4EF",
        color: "#0B1F24",
        fontFamily:
          "Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif",
        position: "relative",
        overflow: "hidden",
      }}
    >
      <div
        style={{
          position: "absolute",
          inset: 0,
          background: `linear-gradient(135deg, rgba(14,111,104,0.20), ${OG_SOFT_MINT} 46%, rgba(184,115,51,0.16))`,
        }}
      />
      <div
        style={{
          position: "absolute",
          right: -90,
          top: 70,
          width: 520,
          height: 520,
          borderRadius: 48,
          background: "#0B1F24",
          opacity: 0.08,
          transform: "rotate(-8deg)",
        }}
      />
      <div
        style={{
          position: "absolute",
          right: 84,
          top: 154,
          width: 430,
          height: 52,
          borderRadius: 999,
          background: "#0E6F68",
          opacity: 0.38,
          transform: "rotate(-15deg)",
        }}
      />
      <div
        style={{
          position: "absolute",
          right: 32,
          top: 245,
          width: 480,
          height: 42,
          borderRadius: 999,
          background: "#5FB7A6",
          opacity: 0.54,
          transform: "rotate(-15deg)",
        }}
      />
      <div
        style={{
          position: "absolute",
          right: 4,
          top: 332,
          width: 390,
          height: 38,
          borderRadius: 999,
          background: "#B87333",
          opacity: 0.58,
          transform: "rotate(-15deg)",
        }}
      />
      <div
        style={{
          position: "relative",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          padding: "72px 82px",
          width: "100%",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 28 }}>
          <OgMark />
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <div
              style={{
                fontFamily: "Georgia, 'Times New Roman', serif",
                fontSize: 56,
                fontWeight: 760,
                letterSpacing: 0,
              }}
            >
              {BRAND.name}
            </div>
            <div
              style={{
                fontSize: 20,
                fontWeight: 700,
                color: "#0E6F68",
                letterSpacing: 1.8,
                textTransform: "uppercase",
              }}
            >
              FTO screening intelligence
            </div>
          </div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 26 }}>
          <div
            style={{
              maxWidth: 800,
              fontSize: 62,
              lineHeight: 1.02,
              fontWeight: 720,
              letterSpacing: 0,
            }}
          >
            Compound-first patent risk, with evidence attached.
          </div>
          <div
            style={{
              display: "flex",
              gap: 14,
              fontSize: 24,
              fontWeight: 700,
              color: "#0B4F4C",
            }}
          >
            <span>Claim maps</span>
            <span style={{ color: "#8A4F1F" }}>•</span>
            <span>potential blocker families</span>
            <span style={{ color: "#8A4F1F" }}>•</span>
            <span>counsel review packets</span>
          </div>
        </div>
      </div>
    </div>,
    size,
  );
}
