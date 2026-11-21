import { useEffect, useState } from "react";

type Me = { signed_in: boolean; linked: boolean; has_access: boolean; name: string | null; roles: string[] };
type State =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; me: Me };

export default function App() {
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    fetch("/api/me")
      .then(async (r) => {
        if (r.status === 401) throw new Error("You are not signed in.");
        if (!r.ok) throw new Error("The server could not be reached. Please try again later.");
        return (await r.json()) as Me;
      })
      .then((me) => setState({ kind: "ready", me }))
      .catch((e: Error) => setState({ kind: "error", message: e.message }));
  }, []);

  return (
    <main className="shell">
      <header>
        <h1>Travel Planner</h1>
        <p className="tagline">Plan field travel early, together, and at lower cost.</p>
      </header>
      <section className="card" aria-live="polite">
        {state.kind === "loading" && <p>Loading…</p>}
        {state.kind === "error" && <p className="problem">{state.message}</p>}
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
      </section>
    </main>
  );
}
