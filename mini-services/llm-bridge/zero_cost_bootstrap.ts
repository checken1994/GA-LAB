/**
 * P0 Z2/Z4 zero-cost bootstrap for the legacy Bun LLM bridge.
 *
 * This file executes BEFORE index.ts and wraps globalThis.fetch. Catalog fetch
 * uses the captured original fetch; inference requests are denied unless a
 * fresh OpenRouter catalog observation proves prompt=0 AND completion=0.
 * Providers without a supported pricing authority (currently Groq) fail closed.
 */

const originalFetch = globalThis.fetch.bind(globalThis);
const CATALOG_URL = "https://openrouter.ai/api/v1/models";
const CATALOG_TTL_MS = 6 * 60 * 60 * 1000;
const CATALOG_TIMEOUT_MS = 5_000;

type PriceEntry = { prompt: number; completion: number };
let catalogExpiresAt = 0;
let catalogPrices = new Map<string, PriceEntry>();
let catalogInflight: Promise<void> | null = null;

function enabled(value: string | undefined): boolean {
  return ["1", "true", "yes", "on"].includes(String(value ?? "").trim().toLowerCase());
}

function validateConfig(): void {
  const mode = String(process.env.SCP_LLM_COST_MODE ?? "free_only").trim().toLowerCase();
  if (mode !== "free_only") throw new Error("[zero-cost] SCP_LLM_COST_MODE must be free_only");
  if (enabled(process.env.SCP_ALLOW_PAID_FALLBACK)) throw new Error("[zero-cost] paid fallback is forbidden");
  if (Number(process.env.SCP_MAX_LLM_COST_USD ?? "0") !== 0) throw new Error("[zero-cost] max LLM cost must equal 0");
  if (process.env.SCP_FREE_REQUIRE_PRICE_PROOF !== undefined && !enabled(process.env.SCP_FREE_REQUIRE_PRICE_PROOF)) {
    throw new Error("[zero-cost] fresh pricing proof cannot be disabled");
  }
  if (process.env.SCP_FREE_FAIL_IF_PRICE_UNKNOWN !== undefined && !enabled(process.env.SCP_FREE_FAIL_IF_PRICE_UNKNOWN)) {
    throw new Error("[zero-cost] unknown pricing must fail closed");
  }
}

async function refreshCatalog(): Promise<void> {
  if (Date.now() < catalogExpiresAt && catalogPrices.size > 0) return;
  if (catalogInflight) return catalogInflight;
  catalogInflight = (async () => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), CATALOG_TIMEOUT_MS);
    try {
      const response = await originalFetch(CATALOG_URL, { signal: controller.signal });
      if (!response.ok) throw new Error(`catalog HTTP ${response.status}`);
      const body: any = await response.json();
      if (!Array.isArray(body?.data)) throw new Error("catalog missing data[]");
      const next = new Map<string, PriceEntry>();
      for (const item of body.data) {
        const id = String(item?.id ?? "");
        const prompt = Number(item?.pricing?.prompt);
        const completion = Number(item?.pricing?.completion);
        if (!id || !Number.isFinite(prompt) || !Number.isFinite(completion)) continue;
        next.set(id, { prompt, completion });
      }
      if (next.size === 0) throw new Error("catalog contained no usable pricing entries");
      catalogPrices = next;
      catalogExpiresAt = Date.now() + CATALOG_TTL_MS;
    } finally {
      clearTimeout(timer);
      catalogInflight = null;
    }
  })();
  return catalogInflight;
}

function targetUrl(input: RequestInfo | URL): URL | null {
  try {
    if (typeof input === "string") return new URL(input);
    if (input instanceof URL) return input;
    if (typeof Request !== "undefined" && input instanceof Request) return new URL(input.url);
  } catch (_) {
    return null;
  }
  return null;
}

async function requestModel(init?: RequestInit): Promise<string> {
  if (!init?.body) return "";
  try {
    const raw = typeof init.body === "string" ? init.body : new TextDecoder().decode(init.body as ArrayBuffer);
    const parsed = JSON.parse(raw);
    return String(parsed?.model ?? "");
  } catch (_) {
    return "";
  }
}

function containsSecretLikePayload(init?: RequestInit): boolean {
  if (typeof init?.body !== "string") return false;
  const body = init.body;
  return /-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----/i.test(body)
    || /\b(?:sk|sk-or-v1)-[A-Za-z0-9_-]{12,}\b/.test(body)
    || /\b(?:password|access[_-]?token|api[_-]?key|secret)\s*[:=]/i.test(body);
}

async function zeroCostFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const url = targetUrl(input);
  if (!url || !url.pathname.endsWith("/chat/completions")) {
    return originalFetch(input as any, init);
  }
  if (containsSecretLikePayload(init)) {
    throw new Error("zero_cost_denied:DENY_DATA_CLASS");
  }
  const model = await requestModel(init);
  if (!model) throw new Error("zero_cost_denied:DENY_UNKNOWN_PRICE");

  if (url.hostname === "openrouter.ai") {
    try {
      await refreshCatalog();
    } catch (_) {
      // No fresh proof: never fall back to an old name/allowlist.
      catalogPrices = new Map();
      catalogExpiresAt = 0;
      throw new Error("zero_cost_denied:DENY_UNKNOWN_PRICE");
    }
    const pricing = catalogPrices.get(model);
    if (!pricing) throw new Error("zero_cost_denied:DENY_UNKNOWN_PRICE");
    if (pricing.prompt !== 0 || pricing.completion !== 0) {
      throw new Error("zero_cost_denied:DENY_PAID");
    }
    return originalFetch(input as any, init);
  }

  // P0 has no independently verified pricing source for this provider.
  throw new Error("zero_cost_denied:DENY_UNKNOWN_PRICE");
}

validateConfig();
(globalThis as any).fetch = zeroCostFetch;
// [Z4] Mark the PEP as installed BEFORE the legacy server loads: core.ts
// refuses to start without this flag, so `bun core.ts` cannot bypass the wall.
(globalThis as any).__SCP_ZERO_COST_PEP__ = true;

await import("./core.ts");
