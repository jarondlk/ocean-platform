import type { MetadataRoute } from "next";

import { PRODUCT_DESCRIPTION, PRODUCT_NAME } from "@/lib/brand";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: PRODUCT_NAME,
    short_name: "OCEAN",
    description: PRODUCT_DESCRIPTION,
    start_url: "/",
    display: "standalone",
    background_color: "#f5fbff",
    theme_color: "#1769aa",
    icons: [
      {
        src: "/ocean-mark.svg",
        sizes: "any",
        type: "image/svg+xml",
      },
    ],
  };
}
