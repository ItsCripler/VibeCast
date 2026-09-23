import { afterEach, describe, expect, it, vi } from "vitest";
import { api, apiPost } from "./api";

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "vibecast_csrf=; Max-Age=0; path=/";
});

describe("API client", () => {
  it("sends cookies and the CSRF token with state-changing requests", async () => {
    document.cookie = "vibecast_csrf=csrf-value; path=/";
    const fetchMock = vi.fn().mockResolvedValue({ status: 200, ok: true, json: async () => ({ id: "playlist" }) });
    vi.stubGlobal("fetch", fetchMock);

    await apiPost("/playlists", { name: "Night drive" });

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const headers = new Headers(init.headers);
    expect(init.credentials).toBe("include");
    expect(headers.get("X-CSRF-Token")).toBe("csrf-value");
    expect(headers.get("Content-Type")).toBe("application/json");
  });

  it("returns undefined for an empty successful response", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ status: 204, ok: true }));
    await expect(api<void>("/playlists/123", { method: "DELETE" })).resolves.toBeUndefined();
  });
});
