/** @type {import('next').NextConfig} */
const backend = process.env.BACKEND_HOSTPORT
  ? `http://${process.env.BACKEND_HOSTPORT}`
  : process.env.BACKEND_URL || "http://localhost:8000";

const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${backend}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
