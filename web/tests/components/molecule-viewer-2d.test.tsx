import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { renderToStaticMarkup } from "react-dom/server";

// Mock the rdkit-loader module
const mockSmilesToSVG = vi.fn();
vi.mock("@/lib/rdkit-loader", () => ({
  loadRDKit: vi.fn(),
  smilesToSVG: (...args: unknown[]) => mockSmilesToSVG(...args),
}));

import { MoleculeViewer2D } from "@/components/chemistry/molecule-viewer-2d";

// RDKit outputs SVG with inline CSS styles
const VALID_SVG =
  '<svg xmlns="http://www.w3.org/2000/svg" width="300" height="200"><rect style="opacity:1.0;fill:#FFFFFF;stroke:none"/><path style="fill:none;fill-rule:evenodd;stroke:#000000;stroke-width:2" d="M10 10 L20 20"/></svg>';
const SVG_WITH_MIXED_COLOR_FORMS =
  '<svg xmlns="http://www.w3.org/2000/svg"><rect fill="white"/><text fill="#000">N</text><path style="fill: #fff; stroke: black;" d="M0 0 L1 1"/><circle stroke="#000000" fill="#ffffff"/></svg>';

describe("MoleculeViewer2D", () => {
  beforeEach(() => {
    mockSmilesToSVG.mockReset();
  });

  // ── Idle state (no async needed) ──────────────────────────────────

  describe("idle state (no SMILES)", () => {
    it("preserves a populated molecular identity in server-rendered markup", () => {
      const html = renderToStaticMarkup(
        <MoleculeViewer2D smiles="O=C(O)CCC(=O)O" label="Succinic acid" />,
      );

      expect(html).toContain("Canonical SMILES");
      expect(html).toContain("O=C(O)CCC(=O)O");
      expect(html).toContain(
        "Interactive structure renders when the molecular viewer loads.",
      );
      expect(html).not.toContain("Enter SMILES to preview");
    });

    it("shows placeholder text when SMILES is empty", () => {
      const { container } = render(<MoleculeViewer2D smiles="" />);
      expect(container.textContent).toContain("Enter SMILES to preview");
    });

    it("shows placeholder for whitespace-only SMILES", () => {
      const { container } = render(<MoleculeViewer2D smiles="   " />);
      expect(container.textContent).toContain("Enter SMILES to preview");
    });

    it("sets aria-busy to false when idle", () => {
      const { container } = render(<MoleculeViewer2D smiles="" />);
      const wrapper = container.firstElementChild;
      expect(wrapper?.getAttribute("aria-busy")).toBe("false");
    });
  });

  // ── Dimension and className props (sync, use never-resolving mock) ─

  describe("dimension props", () => {
    // Use empty SMILES to avoid async import — tests only check container style
    it("keeps the container responsive while honoring max width", () => {
      const { container } = render(<MoleculeViewer2D smiles="" width={400} />);
      const wrapper = container.firstElementChild as HTMLElement;
      expect(wrapper.style.width).toBe("100%");
      expect(wrapper.style.maxWidth).toBe("400px");
    });

    it("uses default max width of 300", () => {
      const { container } = render(<MoleculeViewer2D smiles="" />);
      const wrapper = container.firstElementChild as HTMLElement;
      expect(wrapper.style.width).toBe("100%");
      expect(wrapper.style.maxWidth).toBe("300px");
    });

    it("uses default height of 200", () => {
      const { container } = render(<MoleculeViewer2D smiles="" />);
      const wrapper = container.firstElementChild as HTMLElement;
      expect(wrapper.style.height).toBe("200px");
    });

    it("adjusts height by +32px when label is provided", () => {
      const { container } = render(
        <MoleculeViewer2D smiles="" label="Ethanol" height={200} />,
      );
      const wrapper = container.firstElementChild as HTMLElement;
      expect(wrapper.style.height).toBe("232px");
    });

    it("does not add label height when label is absent", () => {
      const { container } = render(<MoleculeViewer2D smiles="" height={200} />);
      const wrapper = container.firstElementChild as HTMLElement;
      expect(wrapper.style.height).toBe("200px");
    });
  });

  describe("className prop", () => {
    it("applies additional className to wrapper", () => {
      const { container } = render(
        <MoleculeViewer2D smiles="" className="my-custom-class" />,
      );
      const wrapper = container.firstElementChild;
      expect(wrapper?.className).toContain("my-custom-class");
    });
  });

  // ── Rendered state (async) ────────────────────────────────────────

  describe("rendered state", () => {
    it("renders the SVG with role='img' when smilesToSVG succeeds", async () => {
      mockSmilesToSVG.mockResolvedValue(VALID_SVG);
      render(<MoleculeViewer2D smiles="CCO" />);

      expect(
        await screen.findByRole(
          "img",
          { name: "Molecular structure: CCO" },
          { timeout: 5000 },
        ),
      ).toBeInTheDocument();
    });

    it("uses responsive image sizing inside the frame", async () => {
      mockSmilesToSVG.mockResolvedValue(VALID_SVG);
      render(<MoleculeViewer2D smiles="CCO" />);

      expect(
        await screen.findByRole("img", { name: "Molecular structure: CCO" }),
      ).toHaveClass("h-full", "w-full", "object-contain");
    });

    it("sets alt text with SMILES when no label prop", async () => {
      mockSmilesToSVG.mockResolvedValue(VALID_SVG);
      render(<MoleculeViewer2D smiles="CCO" />);

      expect(
        await screen.findByRole("img", { name: "Molecular structure: CCO" }),
      ).toBeInTheDocument();
    });

    it("sets alt text with label prop when provided", async () => {
      mockSmilesToSVG.mockResolvedValue(VALID_SVG);
      render(<MoleculeViewer2D smiles="CCO" label="Ethanol" />);

      expect(
        await screen.findByRole("img", {
          name: "Molecular structure of Ethanol",
        }),
      ).toBeInTheDocument();
    });

    function decodeRenderedSvg(img: HTMLElement) {
      const src = img.getAttribute("src") ?? "";
      return decodeURIComponent(
        src.replace("data:image/svg+xml;charset=utf-8,", ""),
      );
    }

    it("sets aria-busy to false after rendering", async () => {
      mockSmilesToSVG.mockResolvedValue(VALID_SVG);
      const { container } = render(<MoleculeViewer2D smiles="CCO" />);

      await waitFor(() => {
        expect(container.firstElementChild?.getAttribute("aria-busy")).toBe(
          "false",
        );
      });
    });

    it("themes the SVG: replaces white fill with transparent", async () => {
      mockSmilesToSVG.mockResolvedValue(VALID_SVG);
      render(<MoleculeViewer2D smiles="CCO" />);

      const img = await screen.findByRole("img", {
        name: "Molecular structure: CCO",
      });
      const svg = decodeRenderedSvg(img);
      expect(svg).not.toContain("fill:#FFFFFF");
      expect(svg).toContain("fill:transparent");
    });

    it("themes the SVG: replaces black stroke with a concrete Praviar molecule color", async () => {
      mockSmilesToSVG.mockResolvedValue(VALID_SVG);
      render(<MoleculeViewer2D smiles="CCO" />);

      const img = await screen.findByRole("img", {
        name: "Molecular structure: CCO",
      });
      const svg = decodeRenderedSvg(img);
      expect(svg).not.toContain("stroke:#000000");
      expect(svg).toContain("stroke:#0B1F24");
      expect(svg).not.toContain("var(--molecule-stroke)");
    });

    it("themes RDKit SVG color variants into the Praviar molecule palette", async () => {
      mockSmilesToSVG.mockResolvedValue(SVG_WITH_MIXED_COLOR_FORMS);
      render(<MoleculeViewer2D smiles="CCN" />);

      const img = await screen.findByRole("img", {
        name: "Molecular structure: CCN",
      });
      const svg = decodeRenderedSvg(img);
      expect(svg).not.toMatch(/#fff(?:fff)?|white|#000(?:000)?|black/i);
      expect(svg).toContain('fill="transparent"');
      expect(svg).toContain("fill:transparent");
      expect(svg).toContain('fill="#0B1F24"');
      expect(svg).toContain("stroke:#0B1F24");
      expect(svg).toContain('stroke="#0B1F24"');
      expect(svg).not.toContain("var(--");
    });

    it("calls onRender(true) on successful render", async () => {
      mockSmilesToSVG.mockResolvedValue(VALID_SVG);
      const onRender = vi.fn();
      render(<MoleculeViewer2D smiles="CCO" onRender={onRender} />);

      await waitFor(() => {
        expect(onRender).toHaveBeenCalledWith(true);
      });
    });

    it("displays the label text below the structure", async () => {
      mockSmilesToSVG.mockResolvedValue(VALID_SVG);
      const { container } = render(
        <MoleculeViewer2D smiles="CCO" label="Ethanol" />,
      );

      await waitFor(() => {
        expect(container.textContent).toContain("Ethanol");
      });
    });

    it("calls smilesToSVG with smiles + options object containing width/height", async () => {
      mockSmilesToSVG.mockResolvedValue(VALID_SVG);
      render(<MoleculeViewer2D smiles="CCO" width={400} height={300} />);

      // Phase 9: smilesToSVG now accepts an options object so callers can
      // also pass useCXSmiles for Markush rendering.
      await waitFor(() => {
        expect(mockSmilesToSVG).toHaveBeenCalledWith("CCO", {
          width: 400,
          height: 300,
          useCXSmiles: false,
        });
      });
    });

    it("uses default dimensions when not specified", async () => {
      mockSmilesToSVG.mockResolvedValue(VALID_SVG);
      render(<MoleculeViewer2D smiles="CCO" />);

      await waitFor(() => {
        expect(mockSmilesToSVG).toHaveBeenCalledWith("CCO", {
          width: 300,
          height: 200,
          useCXSmiles: false,
        });
      });
    });

    it("passes useCXSmiles=true when isMarkush prop is set", async () => {
      mockSmilesToSVG.mockResolvedValue(VALID_SVG);
      render(<MoleculeViewer2D smiles="[*:1]Cc1ccccc1[*:2]" isMarkush />);

      await waitFor(() => {
        expect(mockSmilesToSVG).toHaveBeenCalledWith("[*:1]Cc1ccccc1[*:2]", {
          width: 300,
          height: 200,
          useCXSmiles: true,
        });
      });
    });
  });

  // ── Invalid SMILES ────────────────────────────────────────────────

  describe("invalid SMILES", () => {
    it("shows 'Invalid SMILES' when smilesToSVG returns null", async () => {
      mockSmilesToSVG.mockResolvedValue(null);
      const { container } = render(
        <MoleculeViewer2D smiles="INVALID_SMILES" />,
      );

      await waitFor(() => {
        expect(container.textContent).toContain("Invalid SMILES");
      });
    });

    it("calls onRender(false) on invalid SMILES", async () => {
      mockSmilesToSVG.mockResolvedValue(null);
      const onRender = vi.fn();
      render(<MoleculeViewer2D smiles="INVALID" onRender={onRender} />);

      await waitFor(() => {
        expect(onRender).toHaveBeenCalledWith(false);
      });
    });
  });

  // ── Error state ───────────────────────────────────────────────────

  describe("error state", () => {
    it("shows user-safe preview guidance when smilesToSVG throws", async () => {
      mockSmilesToSVG.mockRejectedValue(new Error("RDKit failed"));
      vi.spyOn(console, "error").mockImplementation(() => {});

      const { container } = render(<MoleculeViewer2D smiles="CCO" />);

      await waitFor(() => {
        expect(container.textContent).toContain(
          "Structure preview unavailable",
        );
      });

      vi.mocked(console.error).mockRestore();
    });

    it("calls onRender(false) on error", async () => {
      mockSmilesToSVG.mockRejectedValue(new Error("crash"));
      vi.spyOn(console, "error").mockImplementation(() => {});
      const onRender = vi.fn();
      render(<MoleculeViewer2D smiles="CCO" onRender={onRender} />);

      await waitFor(() => {
        expect(onRender).toHaveBeenCalledWith(false);
      });

      vi.mocked(console.error).mockRestore();
    });

    it("avoids developer-facing console instructions in error state", async () => {
      mockSmilesToSVG.mockRejectedValue(new Error("test error"));
      vi.spyOn(console, "error").mockImplementation(() => {});

      const { container } = render(<MoleculeViewer2D smiles="CCO" />);

      await waitFor(() => {
        expect(container.textContent).toContain(
          "Check the compound format or continue without preview.",
        );
        expect(container.textContent).not.toContain("Check console");
      });

      vi.mocked(console.error).mockRestore();
    });
  });

  // ── Loading state (last — uses never-resolving promises) ──────────

  describe("loading state", () => {
    it("shows loading indicator when SMILES is provided", () => {
      mockSmilesToSVG.mockReturnValue(new Promise(() => {}));
      const { container } = render(<MoleculeViewer2D smiles="CCO" />);
      expect(container.textContent).toMatch(/Loading RDKit|Rendering/);
      expect(screen.getByText(/Loading RDKit|Rendering/)).toHaveClass(
        "font-medium",
        "text-[var(--text-secondary)]",
      );
    });

    it("sets aria-busy to true while loading", () => {
      mockSmilesToSVG.mockReturnValue(new Promise(() => {}));
      const { container } = render(<MoleculeViewer2D smiles="CCO" />);
      const wrapper = container.firstElementChild;
      expect(wrapper?.getAttribute("aria-busy")).toBe("true");
    });

    it("does not show loading text when showSkeleton is false", () => {
      mockSmilesToSVG.mockReturnValue(new Promise(() => {}));
      const { container } = render(
        <MoleculeViewer2D smiles="CCO" showSkeleton={false} />,
      );
      expect(container.textContent).not.toMatch(/Loading RDKit/);
    });
  });
});
