import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ShopX AI Support Demo",
  description: "A demo storefront integrated with intelligent customer support.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
