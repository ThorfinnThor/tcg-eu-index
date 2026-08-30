/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  images: {
    remotePatterns: [
      { protocol: "https", hostname: "product-images.s3.cardmarket.com" },
      { protocol: "https", hostname: "cards.scryfall.io" },
      { protocol: "https", hostname: "images.pokemontcg.io" },
      { protocol: "https", hostname: "images.ygoprodeck.com" },
      { protocol: "https", hostname: "product-images.tcgplayer.com" },
      { protocol: "https", hostname: "assets.tcgdex.net" },
      { protocol: "https", hostname: "images.digimoncard.io" },
      { protocol: "https", hostname: "cards.lorcast.io" },
      { protocol: "https", hostname: "cdn.swu-db.com" },
      { protocol: "https", hostname: "storage.googleapis.com" },
      { protocol: "https", hostname: "legendstory-production-s3-public.s3.amazonaws.com" },
      { protocol: "https", hostname: "d2wlb52bya4y8z.cloudfront.net" },
      { protocol: "https", hostname: "en.onepiece-cardgame.com" }
    ]
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
          {
            key: "Content-Security-Policy",
            value: "img-src 'self' data: https://cards.scryfall.io https://product-images.s3.cardmarket.com https://images.pokemontcg.io https://images.ygoprodeck.com https://product-images.tcgplayer.com https://assets.tcgdex.net https://images.digimoncard.io https://cards.lorcast.io https://cdn.swu-db.com https://storage.googleapis.com https://legendstory-production-s3-public.s3.amazonaws.com https://d2wlb52bya4y8z.cloudfront.net https://en.onepiece-cardgame.com"
          }
        ]
      }
    ];
  }
};

export default nextConfig;
