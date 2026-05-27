import type { FormEvent } from "react";
import { useCallback, useState } from "react";
import { publicApi } from "@/api/public";
import { useI18n } from "@/i18n";

export function useNewsletterSubscribe() {
  const { t } = useI18n();
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [subscribeErr, setSubscribeErr] = useState("");

  const onSubscribe = useCallback(
    async (e: FormEvent) => {
      e.preventDefault();
      const trimmed = email.trim();
      if (!trimmed || submitting) return;
      setSubmitting(true);
      setSubscribeErr("");
      try {
        await publicApi.newsletterSubscribe(trimmed);
        setSent(true);
        setEmail("");
        window.setTimeout(() => setSent(false), 4000);
      } catch (err) {
        const text = err instanceof Error && err.message ? err.message : t("newsletterErrorNetwork");
        setSubscribeErr(text);
      } finally {
        setSubmitting(false);
      }
    },
    [email, submitting, t],
  );

  const clearError = useCallback(() => {
    setSubscribeErr("");
  }, []);

  return {
    email,
    setEmail,
    sent,
    submitting,
    subscribeErr,
    clearError,
    onSubscribe,
  };
}
