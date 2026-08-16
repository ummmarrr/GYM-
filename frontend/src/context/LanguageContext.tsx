import React, { createContext, useContext, useEffect, useState } from "react";
import { LANGUAGES, LanguageOption, SupportedLanguage, translations } from "../lib/translations";

interface LanguageContextType {
  language: SupportedLanguage;
  currentLanguage: LanguageOption;
  setLanguage: (lang: SupportedLanguage) => void;
  t: (key: string, fallback?: string) => string;
  languages: LanguageOption[];
}

const LANGUAGE_KEY = "mastergym.language";

const LanguageContext = createContext<LanguageContextType | undefined>(undefined);

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  const [language, setLanguageState] = useState<SupportedLanguage>(() => {
    const saved = localStorage.getItem(LANGUAGE_KEY) as SupportedLanguage | null;
    if (saved && LANGUAGES.some((l) => l.code === saved)) {
      return saved;
    }
    return "en";
  });

  const currentLanguage = LANGUAGES.find((l) => l.code === language) || LANGUAGES[0];

  useEffect(() => {
    localStorage.setItem(LANGUAGE_KEY, language);
    // Update HTML attributes for accessibility and Right-to-Left (RTL) for Urdu
    document.documentElement.lang = language;
    document.documentElement.dir = currentLanguage.isRtl ? "rtl" : "ltr";
  }, [language, currentLanguage]);

  const setLanguage = (lang: SupportedLanguage) => {
    if (LANGUAGES.some((l) => l.code === lang)) {
      setLanguageState(lang);
    }
  };

  const t = (key: string, fallback?: string): string => {
    const langDict = translations[language];
    if (langDict && langDict[key]) {
      return langDict[key];
    }
    // Fallback to English dictionary
    const enDict = translations.en;
    if (enDict && enDict[key]) {
      return enDict[key];
    }
    return fallback || key;
  };

  return (
    <LanguageContext.Provider
      value={{
        language,
        currentLanguage,
        setLanguage,
        t,
        languages: LANGUAGES,
      }}
    >
      {children}
    </LanguageContext.Provider>
  );
}

export function useLanguage(): LanguageContextType {
  const context = useContext(LanguageContext);
  if (!context) {
    throw new Error("useLanguage must be used within a LanguageProvider");
  }
  return context;
}
