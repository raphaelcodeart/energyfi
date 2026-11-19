// The data model is multi-tenant, but this installation hosts a single
// organization (SOSNET), so login and forgot-password send its id without
// asking the user. With a second organization, replace this with a picker or
// server-side resolution by email.
//
// The UUID is the one printed by `python -m app.seed.bootstrap`. It comes from
// NEXT_PUBLIC_DEFAULT_ORGANIZATION_ID in .env and is baked in at BUILD time
// (it is a Dockerfile build arg): after changing it, rebuild the dashboard,
// or every login fails with "credenziali non valide". The fallback is the
// original SOS Affiliate installation (net.mamify.ai).
export const DEFAULT_ORGANIZATION_ID =
  process.env.NEXT_PUBLIC_DEFAULT_ORGANIZATION_ID || "73906813-d8a7-4ba7-b7a5-827c5af5337d";
