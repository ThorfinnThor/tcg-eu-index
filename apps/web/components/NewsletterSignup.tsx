"use client";

import { FormEvent, useState } from "react";

export function NewsletterSignup({ enabled, provider }: { enabled: boolean; provider: string }) {
  const [state, setState] = useState<"idle" | "submitting" | "success" | "error">("idle");
  const [message, setMessage] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setState("submitting");
    const response = await fetch("/api/newsletter", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: form.get("email"), consent: form.get("consent") === "on" })
    });
    const payload = await response.json().catch(() => ({}));
    if (response.ok) {
      setState("success");
      setMessage("Please check your inbox for the provider confirmation.");
      event.currentTarget.reset();
    } else {
      setState("error");
      setMessage(payload.error ?? "Signup failed. Please try again later.");
    }
  }

  return (
    <form className="surface p-5" onSubmit={submit}>
      <h2 className="text-lg font-semibold">Email signup</h2>
      <p className="mt-3 text-sm leading-6 text-paper/60">
        Provider: {provider}. Signup is {enabled ? "enabled" : "disabled"} for this deployment.
      </p>
      <input
        className="surface mt-4 w-full px-3 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-50"
        name="email"
        type="email"
        autoComplete="email"
        placeholder="you@example.com"
        required
        disabled={!enabled || state === "submitting"}
      />
      <label className="mt-3 flex items-start gap-2 text-xs leading-5 text-paper/55">
        <input className="mt-1 h-4 w-4 accent-amber" name="consent" type="checkbox" required disabled={!enabled || state === "submitting"} />
        <span>I agree that my email is sent to the configured newsletter provider for report updates.</span>
      </label>
      <button
        className="mt-3 w-full rounded bg-amber px-3 py-2 text-sm font-semibold text-ink disabled:cursor-not-allowed disabled:opacity-40"
        type="submit"
        disabled={!enabled || state === "submitting"}
      >
        {state === "submitting" ? "Joining..." : "Join"}
      </button>
      {message ? <p className={`mt-3 text-xs leading-5 ${state === "success" ? "text-mint" : "text-coral"}`} role="status">{message}</p> : null}
    </form>
  );
}
