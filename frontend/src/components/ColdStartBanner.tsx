import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";

import { useLanguage } from "../context/LanguageContext";
import { onColdStart } from "../lib/api";

export default function ColdStartBanner() {
  const [waking, setWaking] = useState(false);
  const { t } = useLanguage();

  useEffect(() => onColdStart(setWaking), []);

  if (!waking) return null;

  return (
    <div
      role="status"
      className="fixed inset-x-0 top-16 z-50 mx-auto flex w-fit max-w-[92vw] items-center gap-2.5
        rounded-full border border-volt-500/30 bg-ink-900/95 px-4 py-2 text-sm text-slate-300
        shadow-lg backdrop-blur"
    >
      <Loader2 className="h-4 w-4 shrink-0 animate-spin text-volt-400" aria-hidden />
      <span>{t("coldstart.waking", "Waking the demo server — free hosting sleeps when idle, so give it a minute.")}</span>
    </div>
  );
}
