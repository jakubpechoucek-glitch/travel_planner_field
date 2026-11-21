import { FormEvent, useCallback, useEffect, useState } from "react";

type Me = { signed_in: boolean; linked: boolean; has_access: boolean; name: string | null; roles: string[] };
type State =
  | { kind: "loading" }
  | { kind: "signin" }
  | { kind: "error"; message: string }
  | { kind: "ready"; me: Me };

export default function App() {
  const [state, setState] = useState<State>({ kind: "loading" });

  const load = useCallback(async () => {
    try {
      const r = await fetch("/api/me");
      if (r.status === 401) {
        const mode = (await (await fetch("/api/auth/mode")).json()) as { mode: string };
        setState(
          mode.mode === "passcode"
            ? { kind: "signin" }
            : { kind: "error", message: "You are not signed in. Please open the app from Databricks." },
        );
        return;
      }
      if (!r.ok) throw new Error("The server could not be reached. Please try again later.");
      setState({ kind: "ready", me: (await r.json()) as Me });
    } catch (e) {
      setState({ kind: "error", message: (e as Error).message });
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const signOut = async () => {
    await fetch("/api/auth/logout", { method: "POST" });
    setState({ kind: "signin" });
  };

  return (
    <main className="shell">
      <header>
        <h1>Travel Planner</h1>
        <p className="tagline">Plan field travel early, together, and at lower cost.</p>
      </header>
      <section className="card" aria-live="polite">
        {state.kind === "loading" && <p>Loading…</p>}
        {state.kind === "error" && <p className="problem">{state.message}</p>}
        {state.kind === "signin" && <SignIn onDone={load} />}
        {state.kind === "ready" && !state.me.has_access && (
          <>
            <h2>You do not have access yet</h2>
            <p>
              Your sign-in worked, but your account is not linked to a travel planning role. Please ask
              the Field Collections travel administrator to link your account.
            </p>
          </>
        )}
        {state.kind === "ready" && state.me.has_access && (
          <>
            <h2>Welcome{state.me.name ? `, ${state.me.name}` : ""}</h2>
            <p>Your role: {state.me.roles.join(", ")}</p>
            <p className="muted">The planning calendar is coming in the next phase.</p>
          </>
        )}
        {state.kind === "ready" && (
          <p>
            <button className="link" onClick={signOut}>
              Sign out
            </button>
          </p>
        )}
      </section>
    </main>
  );
}

function SignIn({ onDone }: { onDone: () => void }) {
  const [email, setEmail] = useState("");
  const [passcode, setPasscode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const r = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, passcode }),
    });
    setBusy(false);
    if (r.ok) return onDone();
    const body = (await r.json().catch(() => ({}))) as { detail?: string };
    setError(body.detail ?? "Sign-in failed. Please try again.");
  };

  return (
    <form onSubmit={submit}>
      <h2>Sign in</h2>
      <p className="muted">
        This is a trial installation. Enter your work e-mail and the access code you were given. Your
        e-mail address is not stored; only a one-way code derived from it is kept for the session.
      </p>
      <label>
        Work e-mail
        <input type="email" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />
      </label>
      <label>
        Access code
        <input type="password" required autoComplete="current-password" value={passcode} onChange={(e) => setPasscode(e.target.value)} />
      </label>
      {error && <p className="problem">{error}</p>}
      <button type="submit" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
    </form>
  );
}
