import { env } from "cloudflare:workers";

export async function isRateLimited(key: string, limit = 60) {
  const limiter = limit <= 5 ? env.NEWSLETTER_RATE_LIMITER : env.API_RATE_LIMITER;
  const { success } = await limiter.limit({ key });
  return !success;
}
