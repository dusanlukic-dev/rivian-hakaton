import { clsx, type ClassValue } from "clsx"
import { extendTailwindMerge } from "tailwind-merge"

/**
 * The Vigil type scale and shadow from index.css. Without this, tailwind-merge reads `text-h3` as a text colour
 * and drops it when a real colour (`text-danger`) comes later in the same cn() call
 */
const twMerge = extendTailwindMerge({
  extend: {
    classGroups: {
      "font-size": [{ text: ["display", "score-xl", "h1", "h2", "h3", "body", "body-sm", "label", "caption"] }],
      shadow: [{ shadow: ["float"] }],
    },
  },
})

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
