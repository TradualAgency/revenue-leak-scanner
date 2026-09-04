import { useState, type ReactNode } from "react";
import { ApiError, verifyOperatorKey } from "~/lib/api";
import { setOperatorKey, useOperatorKey } from "~/lib/operatorKey";

// Wraps operator-only screens. The key is entered once per browser session and lives in
// sessionStorage, never in the bundle — see lib/operatorKey.ts for why that matters.
//
// There is no revalidation on mount: a stored key is trusted optimistically. The 403
// handling in api.ts clears it on the first request that actually fails, which flips
// every mounted gate back to locked. Locking the operator out because the backend
// blipped would be worse than one failed request.
export default function OperatorGate({ children }: { children: ReactNode }) {
  const key = useOperatorKey();
  if (!key) return <UnlockForm />;
  return <>{children}</>;
}

function UnlockForm() {
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const candidate = value.trim();
    if (!candidate || checking) return;

    setChecking(true);
    setError(null);
    try {
      // Validate before storing, passing the typed key explicitly — the stored key is
      // still empty at this point. `limit=1` keeps the probe cheap and reuses the
      // endpoint the page is about to call anyway.
      await verifyOperatorKey(candidate);
      setOperatorKey(candidate);
    } catch (err) {
      // Only a 403 means the key is wrong. Anything else (backend down, CORS, network)
      // must not be reported as "wrong key", and must not store the key either.
      setError(
        err instanceof ApiError && err.status === 403
          ? "Ongeldige sleutel."
          : "Backend niet bereikbaar — probeer het opnieuw.",
      );
    } finally {
      setChecking(false);
    }
  }

  return (
    <div className="min-h-screen bg-tradual-bg flex items-center justify-center px-4">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-sm bg-white rounded-2xl shadow-sm border border-gray-100 p-8"
      >
        <span className="inline-block text-xs font-semibold uppercase tracking-widest text-tradual-accent mb-3">
          Intern gebruik
        </span>
        <h1
          className="text-2xl font-semibold text-tradual-primary mb-2"
          style={{ fontFamily: "var(--font-serif)" }}
        >
          Ontgrendelen
        </h1>
        <p className="text-sm text-gray-500 mb-6">
          Voer je operator-sleutel in. Die blijft in deze browsersessie bewaard.
        </p>

        <input
          type="password"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          autoFocus
          placeholder="Operator-sleutel"
          className="w-full border border-gray-200 rounded-lg px-4 py-3 text-sm mb-4 focus:outline-none focus:ring-2 focus:ring-[#c5a96f] focus:border-transparent"
        />

        {error && <p className="text-sm text-[#EF4444] mb-4">{error}</p>}

        <button
          type="submit"
          disabled={checking || value.trim() === ""}
          className="w-full bg-tradual-accent text-tradual-primary font-medium px-8 py-3 hover:opacity-90 transition-opacity disabled:opacity-50"
        >
          {checking ? "Controleren…" : "Ontgrendelen"}
        </button>
      </form>
    </div>
  );
}
