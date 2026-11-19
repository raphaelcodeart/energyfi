import type { MetadataRoute } from "next";

// Web app manifest for Android / PWA "add to home screen". iOS icons come
// from icon.png / apple-icon.png via Next's file conventions.
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "SOS Affiliate · Console",
    short_name: "SOS Affiliate",
    start_url: "/login",
    display: "standalone",
    background_color: "#050b0b",
    theme_color: "#0a54e0",
    icons: [
      { src: "/icon.png", sizes: "512x512", type: "image/png" },
      { src: "/apple-icon.png", sizes: "180x180", type: "image/png" },
    ],
  };
}
