"use client";

import { useSyncExternalStore } from "react";
import { useTheme } from "next-themes";
import { Sun, Moon } from "lucide-react";

const emptySubscribe = () => () => {};

/** True only after the client has mounted. Using useSyncExternalStore rather
 * than the common `useState(false) + useEffect(() => setMounted(true))`
 * idiom -- that pattern trips react-hooks' "no setState in effect body" rule
 * even though it's the documented next-themes idiom, and this is the
 * lint-clean equivalent: the server snapshot is always false, the client
 * snapshot is always true, so React itself schedules the one-time re-render
 * on hydration instead of us doing it via setState. */
function useIsClient() {
  return useSyncExternalStore(
    emptySubscribe,
    () => true,
    () => false,
  );
}

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const isClient = useIsClient();

  if (!isClient) {
    return <div className="h-9 w-9" aria-hidden="true" />;
  }

  const isDark = theme === "dark";

  return (
    <button
      type="button"
      onClick={() => setTheme(isDark ? "light" : "dark")}
      aria-label={isDark ? "Switch to light theme" : "Switch to dark theme"}
      className="flex h-9 w-9 items-center justify-center rounded-lg text-text-muted transition-colors duration-200 hover:bg-surface hover:text-text cursor-pointer"
    >
      {isDark ? <Sun className="h-4 w-4" aria-hidden="true" /> : <Moon className="h-4 w-4" aria-hidden="true" />}
    </button>
  );
}
