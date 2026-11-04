export interface PublicConfig {
  apiBaseUrl: URL;
}

export class ConfigError extends Error {}

/** Validates public env vars at the boundary; fails fast on invalid config. */
export function parsePublicConfig(env: Record<string, string | undefined>): PublicConfig {
  const raw = env.NEXT_PUBLIC_API_URL;
  if (!raw) {
    throw new ConfigError("NEXT_PUBLIC_API_URL is required");
  }
  let url: URL;
  try {
    url = new URL(raw);
  } catch {
    throw new ConfigError("NEXT_PUBLIC_API_URL must be an absolute URL");
  }
  if (url.protocol !== "https:" && url.protocol !== "http:") {
    throw new ConfigError("NEXT_PUBLIC_API_URL must use http or https");
  }
  return { apiBaseUrl: url };
}
