export function requestIp(request: Request) {
  return request.headers.get("cf-connecting-ip")
    || request.headers.get("x-forwarded-for")?.split(",")[0]?.trim()
    || "unknown";
}

export function validPortfolioToken(token: string) {
  return /^[a-f0-9]{32}$/.test(token);
}
