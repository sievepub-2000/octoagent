/**
 * Run `build` or `dev` with `SKIP_ENV_VALIDATION` to skip env validation. This is especially useful
 * for Docker builds.
 */
import "./src/env.js";

/** @type {import("next").NextConfig} */
const allowedDevOrigins = (process.env.NEXT_ALLOWED_DEV_ORIGINS || "192.168.110.2")
  .split(",")
  .map((origin) => origin.trim())
  .filter(Boolean);

const config = {
  devIndicators: false,
  distDir: process.env.NEXT_DIST_DIR || ".next",
  allowedDevOrigins,
};

export default config;
