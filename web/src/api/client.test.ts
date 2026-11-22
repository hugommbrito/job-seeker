import { describe, expect, it, vi } from "vitest";

import { empty, json, serve } from "@/test/server";

import { api, onUnauthorized, readCookie } from "./client";

describe("readCookie", () => {
  it("finds a cookie by its exact name", () => {
    document.cookie = "xcsrftoken=wrong";
    document.cookie = "csrftoken=a%3Db";
    expect(readCookie("csrftoken")).toBe("a=b");
    expect(readCookie("missing")).toBeNull();
  });
});

describe("CSRF", () => {
  it("sends the token on writes and not on reads", async () => {
    document.cookie = "csrftoken=token-1";
    const requests = serve({
      "GET /api/auth/me": () => json(200, { email: "a@example.test", role: "member" }),
      "POST /api/auth/logout": () => empty(),
    });

    await api.GET("/api/auth/me");
    await api.POST("/api/auth/logout");

    expect(requests[0]?.headers.get("X-CSRFToken")).toBeNull();
    expect(requests[1]?.headers.get("X-CSRFToken")).toBe("token-1");
  });

  it("asks the server for the cookie before the first write", async () => {
    const requests = serve({
      "GET /api/auth/csrf": () => {
        document.cookie = "csrftoken=fresh";
        return empty();
      },
      "POST /api/auth/logout": () => empty(),
    });

    await api.POST("/api/auth/logout");

    expect(requests.map((request) => new URL(request.url).pathname)).toEqual([
      "/api/auth/csrf",
      "/api/auth/logout",
    ]);
    expect(requests[1]?.headers.get("X-CSRFToken")).toBe("fresh");
  });
});

describe("session loss", () => {
  it("is announced on 401 and only on 401", async () => {
    const listener = vi.fn();
    const unsubscribe = onUnauthorized(listener);
    serve({
      "GET /api/auth/me": () => json(401, { detail: "Unauthorized" }),
      "GET /api/profile": () => json(403, { detail: "Not available to the demo account." }),
    });

    await api.GET("/api/profile");
    expect(listener).not.toHaveBeenCalled();

    await api.GET("/api/auth/me");
    expect(listener).toHaveBeenCalledTimes(1);

    unsubscribe();
    await api.GET("/api/auth/me");
    expect(listener).toHaveBeenCalledTimes(1);
  });
});
