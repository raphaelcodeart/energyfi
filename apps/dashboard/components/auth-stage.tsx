import Image from "next/image";
import Link from "next/link";
import type { ReactNode } from "react";

/*
 * Shared stage for every screen outside the app: sign-in, password recovery,
 * invitation acceptance, email confirmation. Each page supplies only its form.
 * The stage is always red, even in light theme (see `[data-scene="ember"]` in
 * globals.css). Background layers are empty divs rather than pseudo-elements
 * because there are five of them and a container only has two pseudo-elements.
 */

interface AuthStageProps {
  /** Large heading above the form. */
  title: ReactNode;
  /** Explanatory line under the heading. */
  intro: ReactNode;
  /** Badge text at the top; omit to hide the badge. */
  badge?: string;
  children: ReactNode;
  /** Footer row of the console: service links, notices. */
  footer?: ReactNode;
  /** Console width; forms with more fields read better wide. */
  width?: "normale" | "larga";
}

export function AuthStage({ title, intro, badge, children, footer, width = "normale" }: AuthStageProps) {
  return (
    <main
      data-scene="ember"
      className="flex min-h-screen flex-col items-center justify-center px-4 py-10 sm:px-6"
    >
      {/* --- Background layers, farthest to nearest --- */}
      <div className="stage-beam" aria-hidden="true" />
      <div
        className="stage-orb"
        aria-hidden="true"
        style={{ width: "38rem", height: "38rem", left: "-14rem", top: "-12rem", background: "#216eff" }}
      />
      <div
        className="stage-orb"
        aria-hidden="true"
        style={{
          width: "32rem", height: "32rem", right: "-12rem", bottom: "-10rem",
          background: "#1eb1ff", animationDelay: "-7s",
        }}
      />
      <div className="stage-horizon" aria-hidden="true" />
      <div className="stage-floor" aria-hidden="true" />
      <div className="stage-grain" aria-hidden="true" />

      {/* --- Brand --- */}
      <Link href="/login" className="rise mb-8 inline-flex transition-transform duration-300 hover:scale-[1.03]">
        <Image
          src="/logo-light.png"
          alt="SOS Affiliate"
          width={1200}
          height={231}
          priority
          className="h-11 w-auto drop-shadow-[0_10px_30px_rgba(0,0,0,0.45)] sm:h-14"
        />
      </Link>

      {/* --- Console --- */}
      <section
        className={`pop console w-full p-7 sm:p-10 ${width === "larga" ? "max-w-xl" : "max-w-md"}`}
      >
        {badge && (
          <span className="stage-pill mb-6">
            <i aria-hidden="true" />
            {badge}
          </span>
        )}

        <h1 className="text-[27px] font-extrabold leading-tight tracking-tight text-white sm:text-[32px]">
          {title}
        </h1>
        <p className="mt-2.5 text-sm leading-relaxed text-[#b9cdf0]">{intro}</p>

        <div className="mt-8">{children}</div>

        {footer && <div className="mt-8 border-t border-white/10 pt-6">{footer}</div>}
      </section>

      <p className="mt-8 text-center text-[11px] font-medium tracking-wide text-[#ccdfff] [text-shadow:0_1px_8px_rgba(0,0,0,0.55)]">
        SOSNET · collegamento cifrato · ogni accesso viene registrato
      </p>
    </main>
  );
}

/*
 * --- Shared building blocks for the auth screens: field label, error box,
 * submit button, result screen. ---
 */

export function StageLabel({ htmlFor, children }: { htmlFor?: string; children: ReactNode }) {
  return (
    <label htmlFor={htmlFor} className="block text-[11px] font-bold uppercase tracking-[0.16em] text-[#c6daff]">
      {children}
    </label>
  );
}

/**
 * Alert inside the console. On a red stage a red panel would disappear, so
 * the alert uses black.
 */
export function StageAlert({ children }: { children: ReactNode }) {
  return (
    <div
      role="alert"
      className="pop flex items-start gap-3 rounded-2xl border border-white/25 bg-black/35 p-4 text-sm font-medium text-white"
    >
      <svg className="mt-0.5 h-5 w-5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
        />
      </svg>
      <span>{children}</span>
    </div>
  );
}

/** Main submit button: 64px tall, with sheen and loading spinner. */
export function StageSubmit({
  pending,
  pendingLabel,
  children,
  disabled,
}: {
  pending: boolean;
  pendingLabel: string;
  children: ReactNode;
  disabled?: boolean;
}) {
  return (
    <button type="submit" disabled={pending || disabled} className="btn-xl !mt-7">
      <span className="btn-sheen" aria-hidden="true" />
      {pending ? (
        <>
          <StageSpinner />
          {pendingLabel}
        </>
      ) : (
        <>
          {children}
          <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M13 7l5 5m0 0l-5 5m5-5H6" />
          </svg>
        </>
      )}
    </button>
  );
}

export function StageSpinner({ size = "h-5 w-5" }: { size?: string }) {
  return (
    <svg className={`${size} animate-spin`} fill="none" viewBox="0 0 24 24" aria-hidden="true">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
      />
    </svg>
  );
}

/** Secondary button leading elsewhere: same size, no emphasis. */
export function StageLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <Link href={href} className="btn-ghost-xl">
      {children}
    </Link>
  );
}

/**
 * Result screen: large icon, heading, explanation. `tone` only sets the icon
 * colour; text stays white for contrast on red.
 */
export function StageOutcome({
  tone,
  icon,
  title,
  children,
}: {
  tone: "fatto" | "attesa" | "problema";
  icon: ReactNode;
  title: string;
  children?: ReactNode;
}) {
  const ring =
    tone === "fatto"
      ? "border-success-300/60 text-success-300"
      : tone === "problema"
        ? "border-white/40 text-white"
        : "border-white/30 text-[#c6daff]";

  return (
    <div className="pop text-center">
      <span className={`mx-auto mb-5 grid h-16 w-16 place-items-center rounded-2xl border-2 bg-black/25 ${ring}`}>
        {icon}
      </span>
      <h2 className="text-xl font-extrabold tracking-tight text-white">{title}</h2>
      {children && <div className="mt-2.5 text-sm leading-relaxed text-[#b9cdf0]">{children}</div>}
    </div>
  );
}
