import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async redirects() {
    return [
      // "Thesis" was renamed to "Mandate" in the UI; keep old links working.
      { source: "/thesis", destination: "/mandate", permanent: false },
    ];
  },
};

export default nextConfig;
