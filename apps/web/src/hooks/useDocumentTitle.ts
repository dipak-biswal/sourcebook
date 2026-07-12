import { useEffect } from "react";

/** Sets `document.title` while the component is mounted. */
export function useDocumentTitle(title: string) {
  useEffect(() => {
    const prev = document.title;
    document.title = title.includes("Sourcebook")
      ? title
      : `${title} · Sourcebook`;
    return () => {
      document.title = prev;
    };
  }, [title]);
}
