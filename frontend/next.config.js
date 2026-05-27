/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // PWA client-only: nessun backend, tutto eseguito nel browser via sql.js.
  webpack: (config) => {
    // sql.js usa fs/path in Node ma non nel browser; li disabilitiamo per il bundle client
    config.resolve.fallback = { ...config.resolve.fallback, fs: false, path: false, crypto: false };
    return config;
  },
};

module.exports = nextConfig;
