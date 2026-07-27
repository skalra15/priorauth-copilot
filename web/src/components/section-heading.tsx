import type { ElementType } from "react";

/** Bold section headline, used for every major section heading on the site.
 * Previously paired with a small colored eyebrow label above it -- removed
 * since it read as a generic template label rather than a deliberate design
 * choice -- so this is now just the weight/size treatment: bigger and bolder
 * than plain `font-semibold` body-adjacent text, without extra decoration. */
export function SectionHeading({
  children,
  as: Tag = "h2",
  size = "lg",
}: {
  children: React.ReactNode;
  as?: ElementType;
  size?: "lg" | "md";
}) {
  return (
    <Tag
      className={`mb-3 font-heading font-bold tracking-tight text-text ${
        size === "lg" ? "text-3xl sm:text-4xl" : "text-2xl"
      }`}
    >
      {children}
    </Tag>
  );
}
