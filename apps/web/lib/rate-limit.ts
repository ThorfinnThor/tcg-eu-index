const requests = new Map<string, number[]>();

export async function isRateLimited(key: string, limit = 60, windowMs = 60_000, now = Date.now()) {
  if (requests.size > 10_000) requests.clear();
  const active = (requests.get(key) ?? []).filter((timestamp) => now - timestamp < windowMs);
  active.push(now);
  requests.set(key, active);
  return active.length > limit;
}
