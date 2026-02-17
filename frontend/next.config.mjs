/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    const backend = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
  // Increase timeout for API routes (voice-chat can take longer due to STT/RAG/TTS)
  experimental: {
    proxyTimeout: 120000, // 2 minutes
  },
};

export default nextConfig;
