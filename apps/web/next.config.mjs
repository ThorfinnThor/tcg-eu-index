const remoteImageHosts = [
  "product-images.s3.cardmarket.com",
  "cards.scryfall.io",
  "images.pokemontcg.io",
  "images.ygoprodeck.com",
  "product-images.tcgplayer.com",
  "assets.tcgdex.net",
  "images.digimoncard.io",
  "cards.lorcast.io",
  "cdn.swu-db.com",
  "storage.googleapis.com",
  "legendstory-production-s3-public.s3.amazonaws.com",
  "d2wlb52bya4y8z.cloudfront.net",
  "cmsassets.rgpub.io",
  "en.onepiece-cardgame.com",
];

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  images: {
    remotePatterns: remoteImageHosts.map((hostname) => ({ protocol: "https", hostname }))
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
            value: `img-src 'self' data: ${remoteImageHosts.map((hostname) => `https://${hostname}`).join(" ")}`
          }
        ]
      }
    ];
  }
};

export default nextConfig;
