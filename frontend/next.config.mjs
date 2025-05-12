/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://localhost:8000/:path*", // Proxy to Backend
      },
      {
        source: "/ws/:path*",
        destination: "http://localhost:8000/ws/:path*", // Proxy for WebSockets
      },
    ];
  },
};

export default nextConfig;
