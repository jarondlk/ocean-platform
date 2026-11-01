/** Explicit host-only transport adapter. Existing preview/client defaults stay credential-free. */
export function sessionFetcher(fetcher: typeof fetch = fetch) {
  return async (input: string, init: RequestInit = {}): Promise<Response> => {
    if (!(input === "/v1/runtime" || input.startsWith("/catalogue/") || input.startsWith("/research/")) || /[\\\x00-\x20#]/.test(input)
        || input.startsWith("//") || input.includes("%") || input.includes("?") || /\/(?:\.\.?)(?:\/|$)/.test(input)) throw new Error("Invalid v1 host request");
    const headers = new Headers(init.headers);
    if (headers.has("authorization")) throw new Error("Browser bearer tokens are not accepted by the v1 host");
    return fetcher(input, { ...init, credentials: "same-origin", cache: "no-store", redirect: "error", headers });
  };
}
