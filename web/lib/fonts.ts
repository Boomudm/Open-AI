import { Noto_Sans_Thai, Roboto } from "next/font/google";

/** Latin UI — close to Google Gemini / Material sans. */
export const roboto = Roboto({
  subsets: ["latin"],
  weight: ["400", "500", "700"],
  variable: "--font-sans",
  display: "swap",
});

/** Thai glyphs — pairs with Roboto for mixed TH/EN chat. */
export const notoSansThai = Noto_Sans_Thai({
  subsets: ["thai", "latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-sans-thai",
  display: "swap",
});

export const fontClassNames = `${roboto.variable} ${notoSansThai.variable}`;
