import { afterEach, describe, expect, it, vi } from "vitest";

describe("loadRDKit", () => {
  afterEach(() => {
    delete window.initRDKitModule;
    vi.resetModules();
  });

  it("clears a failed initialization promise so a transient WASM abort can retry", async () => {
    const rdkitModuleStub = {
      prefer_coordgen: vi.fn(),
      version: () => "test",
    };
    window.initRDKitModule = vi
      .fn()
      .mockRejectedValueOnce(new Error("streaming compilation aborted"))
      .mockResolvedValueOnce(rdkitModuleStub);

    const { loadRDKit } = await import("@/lib/rdkit-loader");
    await expect(loadRDKit()).rejects.toThrow("streaming compilation aborted");
    await expect(loadRDKit()).resolves.toBe(rdkitModuleStub);
    expect(window.initRDKitModule).toHaveBeenCalledTimes(2);
    expect(rdkitModuleStub.prefer_coordgen).toHaveBeenCalledWith(true);
  });
});
