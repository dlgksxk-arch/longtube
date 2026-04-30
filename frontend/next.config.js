/** @type {import('next').NextConfig} */
const isDev = process.env.NODE_ENV !== "production";

const nextConfig = {
  // `next dev` and `next build` must not share the same output directory.
  // If they both write into `.next`, the running dev server can lose its CSS assets
  // and the page falls back to unstyled HTML.
  distDir: isDev ? ".next-dev" : ".next",
};

module.exports = nextConfig;
