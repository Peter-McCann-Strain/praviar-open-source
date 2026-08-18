import { readFileSync } from "node:fs";
import { join } from "node:path";
import { inflateSync } from "node:zlib";
import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  PRAVIAR_MARK_BAND_PATHS,
  PRAVIAR_MARK_COLOR_FILLS,
  PRAVIAR_MARK_ID,
  PRAVIAR_MARK_INK_PATH,
  PRAVIAR_MARK_ON_DARK_FILLS,
  PRAVIAR_MARK_ON_LIGHT_FILLS,
  PRAVIAR_MARK_ON_LIGHT_OUTLINE,
  PRAVIAR_MARK_TILE_PATH,
  PRAVIAR_MARK_VIEWBOX,
  PraviarMark,
} from "@/components/icons/praviar-mark";

const MASTER_GEOMETRY = [
  PRAVIAR_MARK_TILE_PATH,
  PRAVIAR_MARK_INK_PATH,
  ...PRAVIAR_MARK_BAND_PATHS,
];

const MASTER_STATIC_PATHS = [
  { d: PRAVIAR_MARK_TILE_PATH, fill: PRAVIAR_MARK_ON_LIGHT_FILLS.paper },
  { d: PRAVIAR_MARK_INK_PATH, fill: PRAVIAR_MARK_ON_LIGHT_FILLS.ink },
  { d: PRAVIAR_MARK_BAND_PATHS[0], fill: PRAVIAR_MARK_ON_LIGHT_FILLS.mint },
  { d: PRAVIAR_MARK_BAND_PATHS[1], fill: PRAVIAR_MARK_ON_LIGHT_FILLS.teal },
  { d: PRAVIAR_MARK_BAND_PATHS[2], fill: PRAVIAR_MARK_ON_LIGHT_FILLS.copper },
  {
    d: PRAVIAR_MARK_BAND_PATHS[3],
    fill: PRAVIAR_MARK_ON_LIGHT_FILLS.softMint,
  },
] as const;

const PUBLIC_STATIC_MARK_ASSETS = [
  { path: "public/brand/praviar-mark.svg", outlined: false },
  { path: "public/brand/praviar-mark-on-light.svg", outlined: true },
  { path: "public/brand/praviar-mark-on-dark.svg", outlined: false },
  { path: "src/app/icon.svg", outlined: false },
  {
    path: "../praviar_pipeline/src/praviar_pipeline/rendering/templates/brand/praviar-mark.svg",
    outlined: false,
  },
  {
    path: "../praviar_pipeline/src/praviar_pipeline/rendering/templates/brand/praviar-mark-on-light.svg",
    outlined: true,
  },
] as const;

function readAttribute(attributes: string, name: string) {
  const match = attributes.match(new RegExp(`${name}="([^"]+)"`, "u"));
  return match?.[1];
}

function extractPathTuples(svg: string) {
  return [...svg.matchAll(/<path\b([^>]*)\/?>/gu)].map((match) => {
    const attributes = match[1] ?? "";
    const tuple: {
      d: string | undefined;
      fill: string | undefined;
      stroke?: string;
      strokeWidth?: string;
    } = {
      d: readAttribute(attributes, "d"),
      fill: readAttribute(attributes, "fill"),
    };
    const stroke = readAttribute(attributes, "stroke");
    const strokeWidth = readAttribute(attributes, "stroke-width");

    if (stroke) {
      tuple.stroke = stroke;
    }
    if (strokeWidth) {
      tuple.strokeWidth = strokeWidth;
    }

    return tuple;
  });
}

function readIcoEntries(favicon: Buffer) {
  const iconCount = favicon.readUInt16LE(4);
  return Array.from({ length: iconCount }, (_, index) => {
    const offset = 6 + index * 16;
    const width = favicon[offset] === 0 ? 256 : favicon[offset];
    const height = favicon[offset + 1] === 0 ? 256 : favicon[offset + 1];
    const byteLength = favicon.readUInt32LE(offset + 8);
    const imageOffset = favicon.readUInt32LE(offset + 12);

    return {
      width,
      height,
      image: favicon.subarray(imageOffset, imageOffset + byteLength),
    };
  });
}

function readDibPixel(
  image: Buffer,
  width: number,
  height: number,
  x: number,
  y: number,
) {
  const headerLength = image.readUInt32LE(0);
  const bitsPerPixel = image.readUInt16LE(14);
  expect(bitsPerPixel).toBe(32);

  const row = height - 1 - y;
  const pixelOffset = headerLength + (row * width + x) * 4;
  const blue = image[pixelOffset] ?? 0;
  const green = image[pixelOffset + 1] ?? 0;
  const red = image[pixelOffset + 2] ?? 0;
  const alpha = image[pixelOffset + 3] ?? 0;

  return { red, green, blue, alpha };
}

function readPngDimensions(png: Buffer) {
  expect(png.subarray(0, 8).toString("hex")).toBe("89504e470d0a1a0a");

  return {
    width: png.readUInt32BE(16),
    height: png.readUInt32BE(20),
  };
}

type PngPixels = {
  height: number;
  pixels: Buffer;
  width: number;
};

type Rgb = readonly [number, number, number];

type ColorCluster = {
  centerX: number;
  centerY: number;
  count: number;
  ratio: number;
};

type PixelRegion = (x: number, y: number) => boolean;

const PNG_SIGNATURE = "89504e470d0a1a0a";
const PRAVIAR_APP_ICON_COLORS = {
  copper: [184, 115, 51],
  dark: [11, 31, 36],
  mint: [95, 183, 166],
  paper: [246, 244, 239],
  softMint: [215, 236, 229],
  teal: [14, 111, 104],
} as const satisfies Record<string, Rgb>;

function paethPredictor(left: number, up: number, upperLeft: number) {
  const estimate = left + up - upperLeft;
  const leftDistance = Math.abs(estimate - left);
  const upDistance = Math.abs(estimate - up);
  const upperLeftDistance = Math.abs(estimate - upperLeft);

  if (leftDistance <= upDistance && leftDistance <= upperLeftDistance) {
    return left;
  }

  return upDistance <= upperLeftDistance ? up : upperLeft;
}

function decodePngPixels(png: Buffer): PngPixels {
  expect(png.subarray(0, 8).toString("hex")).toBe(PNG_SIGNATURE);

  let offset = 8;
  let width = 0;
  let height = 0;
  let bitDepth = 0;
  let colorType = 0;
  const idatChunks: Buffer[] = [];

  while (offset < png.length) {
    const chunkLength = png.readUInt32BE(offset);
    const chunkType = png.subarray(offset + 4, offset + 8).toString("ascii");
    const chunk = png.subarray(offset + 8, offset + 8 + chunkLength);
    offset += 12 + chunkLength;

    if (chunkType === "IHDR") {
      width = chunk.readUInt32BE(0);
      height = chunk.readUInt32BE(4);
      bitDepth = chunk[8] ?? 0;
      colorType = chunk[9] ?? 0;
    } else if (chunkType === "IDAT") {
      idatChunks.push(chunk);
    } else if (chunkType === "IEND") {
      break;
    }
  }

  expect(bitDepth, "PNG icons should use 8-bit channels").toBe(8);
  expect([2, 6], "PNG icons should be RGB or RGBA").toContain(colorType);

  const channelCount = colorType === 6 ? 4 : 3;
  const rowStride = width * channelCount;
  const inflated = inflateSync(Buffer.concat(idatChunks));
  const previousRow = Buffer.alloc(rowStride);
  const pixels = Buffer.alloc(width * height * 4);
  let readOffset = 0;

  for (let y = 0; y < height; y += 1) {
    const filter = inflated[readOffset];
    readOffset += 1;
    const row = Buffer.from(
      inflated.subarray(readOffset, readOffset + rowStride),
    );
    readOffset += rowStride;

    for (let index = 0; index < rowStride; index += 1) {
      const left = index >= channelCount ? (row[index - channelCount] ?? 0) : 0;
      const up = previousRow[index] ?? 0;
      const upperLeft =
        index >= channelCount ? (previousRow[index - channelCount] ?? 0) : 0;
      let value = row[index] ?? 0;

      if (filter === 1) {
        value += left;
      } else if (filter === 2) {
        value += up;
      } else if (filter === 3) {
        value += Math.floor((left + up) / 2);
      } else if (filter === 4) {
        value += paethPredictor(left, up, upperLeft);
      } else {
        expect(filter, "Unsupported PNG scanline filter").toBe(0);
      }

      row[index] = value & 255;
    }

    row.copy(previousRow);
    for (let x = 0; x < width; x += 1) {
      const sourceIndex = x * channelCount;
      const targetIndex = (y * width + x) * 4;

      pixels[targetIndex] = row[sourceIndex] ?? 0;
      pixels[targetIndex + 1] = row[sourceIndex + 1] ?? 0;
      pixels[targetIndex + 2] = row[sourceIndex + 2] ?? 0;
      pixels[targetIndex + 3] =
        channelCount === 4 ? (row[sourceIndex + 3] ?? 255) : 255;
    }
  }

  return { width, height, pixels };
}

function colorDistance(
  red: number,
  green: number,
  blue: number,
  [targetRed, targetGreen, targetBlue]: Rgb,
) {
  return Math.hypot(red - targetRed, green - targetGreen, blue - targetBlue);
}

function colorCluster(
  image: PngPixels,
  color: Rgb,
  tolerance = 16,
  region?: PixelRegion,
): ColorCluster {
  let count = 0;
  let denominator = 0;
  let xSum = 0;
  let ySum = 0;

  for (let y = 0; y < image.height; y += 1) {
    for (let x = 0; x < image.width; x += 1) {
      if (region && !region(x, y)) continue;
      denominator += 1;
      const index = (y * image.width + x) * 4;
      const alpha = image.pixels[index + 3] ?? 0;
      if (alpha === 0) continue;
      if (
        colorDistance(
          image.pixels[index] ?? 0,
          image.pixels[index + 1] ?? 0,
          image.pixels[index + 2] ?? 0,
          color,
        ) > tolerance
      ) {
        continue;
      }

      count += 1;
      xSum += x;
      ySum += y;
    }
  }

  return {
    centerX: count === 0 ? 0 : xSum / count / image.width,
    centerY: count === 0 ? 0 : ySum / count / image.height,
    count,
    ratio: count / (denominator || image.width * image.height),
  };
}

function alphaAt(image: PngPixels, xRatio: number, yRatio: number) {
  const x = Math.round(xRatio * (image.width - 1));
  const y = Math.round(yRatio * (image.height - 1));
  return image.pixels[(y * image.width + x) * 4 + 3] ?? 0;
}

function opaqueRatio(image: PngPixels) {
  let opaque = 0;

  for (let index = 3; index < image.pixels.length; index += 4) {
    if ((image.pixels[index] ?? 0) >= 250) opaque += 1;
  }

  return opaque / (image.width * image.height);
}

describe("PraviarMark", () => {
  it("renders the Praviar evidence mark with the public size API", () => {
    const { container } = render(
      <PraviarMark size={32} className="text-brand-primary" />,
    );

    const svg = container.querySelector(
      `svg[data-praviar-mark="${PRAVIAR_MARK_ID}"]`,
    );
    const paths = container.querySelectorAll("path");

    expect(svg).toBeInTheDocument();
    expect(svg).toHaveAttribute("width", "32");
    expect(svg).toHaveAttribute("height", "32");
    expect(svg).toHaveAttribute("viewBox", PRAVIAR_MARK_VIEWBOX);
    expect(paths).toHaveLength(MASTER_GEOMETRY.length);

    expect(paths[0]).toHaveAttribute("d", PRAVIAR_MARK_TILE_PATH);
    expect(paths[0]).toHaveAttribute("fill", PRAVIAR_MARK_COLOR_FILLS.paper);
    expect(paths[1]).toHaveAttribute("d", PRAVIAR_MARK_INK_PATH);
    expect(paths[1]).toHaveAttribute("fill", PRAVIAR_MARK_COLOR_FILLS.ink);
    expect(paths[2]).toHaveAttribute("fill", PRAVIAR_MARK_COLOR_FILLS.mint);
    expect(paths[3]).toHaveAttribute("fill", PRAVIAR_MARK_COLOR_FILLS.teal);
    expect(paths[4]).toHaveAttribute("fill", PRAVIAR_MARK_COLOR_FILLS.copper);
    expect(paths[5]).toHaveAttribute("fill", PRAVIAR_MARK_COLOR_FILLS.softMint);

    PRAVIAR_MARK_BAND_PATHS.forEach((path, index) => {
      expect(paths[index + 2]).toHaveAttribute("d", path);
    });
  });

  it("keeps every supported colorway on the full canonical evidence geometry", () => {
    for (const variant of ["color", "onLight", "onDark"] as const) {
      const { container, unmount } = render(<PraviarMark variant={variant} />);
      const paths = container.querySelectorAll("path");

      expect(paths).toHaveLength(MASTER_GEOMETRY.length);
      expect(paths[0]).toHaveAttribute("d", PRAVIAR_MARK_TILE_PATH);
      expect(paths[1]).toHaveAttribute("d", PRAVIAR_MARK_INK_PATH);
      PRAVIAR_MARK_BAND_PATHS.forEach((path, index) => {
        expect(paths[index + 2]).toHaveAttribute("d", path);
      });

      unmount();
    }
  });

  it("supports explicit on-light and on-dark colorways for nested surfaces", () => {
    const light = render(<PraviarMark variant="onLight" />);
    const dark = render(<PraviarMark variant="onDark" />);

    const lightPaths = light.container.querySelectorAll("path");
    const darkPaths = dark.container.querySelectorAll("path");

    expect(lightPaths[0]).toHaveAttribute(
      "fill",
      PRAVIAR_MARK_ON_LIGHT_FILLS.paper,
    );
    expect(lightPaths[0]).toHaveAttribute(
      "stroke",
      PRAVIAR_MARK_ON_LIGHT_OUTLINE,
    );
    expect(lightPaths[1]).toHaveAttribute(
      "fill",
      PRAVIAR_MARK_ON_LIGHT_FILLS.ink,
    );
    expect(lightPaths[4]).toHaveAttribute(
      "fill",
      PRAVIAR_MARK_ON_LIGHT_FILLS.copper,
    );
    expect(darkPaths[0]).toHaveAttribute(
      "fill",
      PRAVIAR_MARK_ON_DARK_FILLS.paper,
    );
    expect(darkPaths[1]).toHaveAttribute(
      "fill",
      PRAVIAR_MARK_ON_DARK_FILLS.ink,
    );
    expect(darkPaths[4]).toHaveAttribute(
      "fill",
      PRAVIAR_MARK_ON_DARK_FILLS.copper,
    );
  });

  it("keeps static brand and app icon assets on the same master geometry", () => {
    const staticMark = readFileSync(
      join(process.cwd(), "public/brand/praviar-mark.svg"),
      "utf8",
    );
    const appIcon = readFileSync(
      join(process.cwd(), "src/app/icon.svg"),
      "utf8",
    );
    const markOnLight = readFileSync(
      join(process.cwd(), "public/brand/praviar-mark-on-light.svg"),
      "utf8",
    );
    const markOnDark = readFileSync(
      join(process.cwd(), "public/brand/praviar-mark-on-dark.svg"),
      "utf8",
    );

    for (const asset of [staticMark, appIcon, markOnLight, markOnDark]) {
      for (const path of MASTER_GEOMETRY) {
        expect(asset).toContain(path);
      }

      expect(asset).not.toMatch(/<polygon\b/);
      expect(asset).not.toMatch(/<line\b/);
      expect(asset).not.toMatch(/<polyline\b/);
      expect(asset).not.toContain("clipPath");
      expect(asset).not.toContain("mask");
    }

    expect(staticMark).not.toContain("<rect");
    expect(staticMark).not.toContain("<linearGradient");
    expect(staticMark).not.toContain("<radialGradient");
    expect(appIcon).toContain("<rect");
    expect(appIcon).toContain("<radialGradient");
  });

  it("keeps every public static SVG mark on the exact canonical path and paint tuples", () => {
    for (const asset of PUBLIC_STATIC_MARK_ASSETS) {
      const svg = readFileSync(join(process.cwd(), asset.path), "utf8");
      const expectedPaths = MASTER_STATIC_PATHS.map((path, index) =>
        asset.outlined && index === 0
          ? {
              ...path,
              stroke: PRAVIAR_MARK_ON_LIGHT_OUTLINE,
              strokeWidth: "4",
            }
          : path,
      );

      expect(svg, `${asset.path} must use the Praviar mark viewBox`).toContain(
        `viewBox="${PRAVIAR_MARK_VIEWBOX}"`,
      );
      expect(extractPathTuples(svg), asset.path).toEqual(expectedPaths);
      expect(
        svg,
        `${asset.path} must not contain retired ring geometry`,
      ).not.toMatch(
        /hex|ring|window|windows|shield|scale|gavel|molecule|benzene/i,
      );
    }
  });

  it("keeps the mark on the approved Praviar evidence geometry", () => {
    const staticMark = readFileSync(
      join(process.cwd(), "public/brand/praviar-mark.svg"),
      "utf8",
    );
    const combinedGeometry = MASTER_GEOMETRY.join(" ");
    const staticPathCount = staticMark.match(/<path\b/g)?.length ?? 0;

    expect(PRAVIAR_MARK_ID).toBe("praviar-evidence-mark");
    expect(staticPathCount).toBe(MASTER_GEOMETRY.length);
    expect(staticMark).toContain("Praviar evidence mark");
    expect(combinedGeometry).toContain("M48 34H156");
    expect(combinedGeometry).toContain("C122 85 158 101 210 80");
    expect(combinedGeometry).toContain("C158 172 185 158 211 142");
    expect(staticMark).not.toMatch(
      /hex|ring|window|windows|shield|scale|gavel|molecule|benzene/i,
    );
  });

  it("ships a generated favicon with the controlled app icon sizes", () => {
    const favicon = readFileSync(join(process.cwd(), "src/app/favicon.ico"));
    const entries = readIcoEntries(favicon);
    const sizes = new Set(entries.map(({ width }) => width));

    expect(favicon.readUInt16LE(0)).toBe(0);
    expect(favicon.readUInt16LE(2)).toBe(1);
    expect(entries).toHaveLength(4);
    expect(sizes).toEqual(new Set([16, 32, 48, 64]));
  });

  it("keeps the favicon on the dark rounded app icon, not the transparent mark-only asset", () => {
    const favicon = readFileSync(join(process.cwd(), "src/app/favicon.ico"));
    const largeIcon = readIcoEntries(favicon).find(
      ({ width, height }) => width === 64 && height === 64,
    );

    expect(largeIcon).toBeDefined();

    const topBackground = readDibPixel(largeIcon!.image, 64, 64, 32, 8);
    const leftBackground = readDibPixel(largeIcon!.image, 64, 64, 8, 32);

    for (const pixel of [topBackground, leftBackground]) {
      expect(pixel.alpha).toBe(255);
      expect(pixel.red).toBeGreaterThanOrEqual(8);
      expect(pixel.red).toBeLessThanOrEqual(18);
      expect(pixel.green).toBeGreaterThanOrEqual(40);
      expect(pixel.green).toBeLessThanOrEqual(65);
      expect(pixel.blue).toBeGreaterThanOrEqual(40);
      expect(pixel.blue).toBeLessThanOrEqual(65);
    }
  });

  it("ships touch and install PNG icons from the canonical Praviar app icon", () => {
    const iconAssets = [
      { maskable: false, path: "src/app/apple-icon.png", size: 180 },
      { maskable: false, path: "public/icons/praviar-icon-192.png", size: 192 },
      { maskable: false, path: "public/icons/praviar-icon-512.png", size: 512 },
      {
        maskable: true,
        path: "public/icons/praviar-maskable-512.png",
        size: 512,
      },
    ] as const;

    for (const { maskable, path, size } of iconAssets) {
      const png = readFileSync(join(process.cwd(), path));
      const image = decodePngPixels(png);
      const dark = colorCluster(image, PRAVIAR_APP_ICON_COLORS.dark);
      const paper = colorCluster(image, PRAVIAR_APP_ICON_COLORS.paper);
      const mint = colorCluster(image, PRAVIAR_APP_ICON_COLORS.mint);
      const teal = colorCluster(image, PRAVIAR_APP_ICON_COLORS.teal);
      const copper = colorCluster(image, PRAVIAR_APP_ICON_COLORS.copper);
      const softMint = colorCluster(image, PRAVIAR_APP_ICON_COLORS.softMint);
      const safeCircle: PixelRegion = (x, y) => {
        const normalizedX = (x + 0.5) / image.width;
        const normalizedY = (y + 0.5) / image.height;
        return Math.hypot(normalizedX - 0.5, normalizedY - 0.5) <= 0.4;
      };

      expect(readPngDimensions(png)).toEqual({
        width: size,
        height: size,
      });
      expect(
        opaqueRatio(image),
        `${path} should render with the expected app-icon alpha treatment`,
      ).toBeGreaterThan(maskable ? 0.99 : 0.92);
      expect(
        alphaAt(image, 0.02, 0.02),
        `${path} should have purpose-appropriate corner alpha`,
      ).toBe(maskable ? 255 : 0);
      expect(
        alphaAt(image, 0.98, 0.98),
        `${path} should have purpose-appropriate opposite-corner alpha`,
      ).toBe(maskable ? 255 : 0);
      expect(
        dark.ratio,
        `${path} should include the Ink app tile/silhouette`,
      ).toBeGreaterThan(maskable ? 0.48 : 0.35);
      expect(
        paper.ratio,
        `${path} should include the Paper Praviar tile`,
      ).toBeGreaterThan(maskable ? 0.1 : 0.24);
      expect(
        mint.ratio,
        `${path} should include the mint band`,
      ).toBeGreaterThan(0.01);
      expect(
        teal.ratio,
        `${path} should include the teal band`,
      ).toBeGreaterThan(0.012);
      expect(
        copper.ratio,
        `${path} should include the copper band`,
      ).toBeGreaterThan(0.012);
      expect(
        softMint.ratio,
        `${path} should include the soft-mint terminal band`,
      ).toBeGreaterThan(0.005);

      if (maskable) {
        expect(
          colorCluster(image, PRAVIAR_APP_ICON_COLORS.paper, 16, safeCircle)
            .ratio,
          `${path} should keep the Paper tile visible inside common masks`,
        ).toBeGreaterThan(0.2);
        expect(
          colorCluster(image, PRAVIAR_APP_ICON_COLORS.mint, 16, safeCircle)
            .ratio,
          `${path} should keep the mint band visible inside common masks`,
        ).toBeGreaterThan(0.02);
        expect(
          colorCluster(image, PRAVIAR_APP_ICON_COLORS.teal, 16, safeCircle)
            .ratio,
          `${path} should keep the teal band visible inside common masks`,
        ).toBeGreaterThan(0.02);
        expect(
          colorCluster(image, PRAVIAR_APP_ICON_COLORS.copper, 16, safeCircle)
            .ratio,
          `${path} should keep the copper band visible inside common masks`,
        ).toBeGreaterThan(0.02);
      }

      expect(
        mint.centerX,
        `${path} mint band should sit on the right side`,
      ).toBeGreaterThan(0.55);
      expect(
        teal.centerX,
        `${path} teal band should sit on the right side`,
      ).toBeGreaterThan(0.55);
      expect(
        copper.centerX,
        `${path} copper band should sit on the right side`,
      ).toBeGreaterThan(0.55);
      expect(
        softMint.centerX,
        `${path} soft-mint band should sit on the right side`,
      ).toBeGreaterThan(0.55);
      expect(
        teal.centerY,
        `${path} teal band should sit below mint`,
      ).toBeGreaterThan(mint.centerY);
      expect(
        copper.centerY,
        `${path} copper band should sit below teal`,
      ).toBeGreaterThan(teal.centerY);
      expect(
        softMint.centerY,
        `${path} soft-mint band should sit below copper`,
      ).toBeGreaterThan(copper.centerY);
    }
  });
});
