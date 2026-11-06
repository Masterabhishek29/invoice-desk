import { fileURLToPath } from 'node:url';
const nextConfig = {
  ...(process.env.STATIC_EXPORT === '1' ? { output: 'export' } : {}),
  experimental: { proxyTimeout: 120000 },
  turbopack: { root: fileURLToPath(new URL('.', import.meta.url)) },
  ...(process.env.STATIC_EXPORT === '1' ? {} : {
    async rewrites() {
      return [{ source: '/api/:path*', destination: `${process.env.PYTHON_API_URL || 'http://127.0.0.1:8000'}/api/:path*` }];
    },
  }),
};
export default nextConfig;
