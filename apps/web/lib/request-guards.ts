const requests = new Map<string, number[]>();

export function requestIp(request: Request) {
  return request.headers.get("x-forwarded-for")?.split(",")[0]?.trim() || "unknown";
}

export function isRateLimited(key: string, limit = 60, windowMs = 60_000, now = Date.now()) {
  if (requests.size > 10_000) requests.clear();
  const active = (requests.get(key) ?? []).filter((timestamp) => now - timestamp < windowMs);
  active.push(now);
  requests.set(key, active);
  return active.length > limit;
}

export function validPortfolioToken(token: string) {
  return /^[a-f0-9]{32}$/.test(token);
}
