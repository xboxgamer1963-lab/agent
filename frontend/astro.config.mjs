import { defineConfig } from 'astro/config';

// Minimal static-output config. Tailwind is intentionally NOT wired up as a
// build-time integration here — both pages load Tailwind via the CDN script
// and each defines its own inline tailwind.config, since they are two
// separate, conflicting design systems (marketing site vs. app dashboard).
//
// cssMinify is disabled so the `is:global` <style> blocks pass through
// byte-for-byte instead of being re-serialized by Vite's CSS minifier
// (which otherwise rewrites colors, reorders declarations, and can drop
// "redundant-looking" vendor-prefixed properties like
// -webkit-background-clip — a real behavior change on older WebKit).
export default defineConfig({
  vite: {
    build: {
      cssMinify: false,
    },
  },
});
