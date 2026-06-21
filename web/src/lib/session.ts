const KEY = "openrole_session";

export type OpenRoleSession = {
  jobId: string | null;
  step: string;
};

const DEFAULT: OpenRoleSession = { jobId: null, step: "research" };

export function loadSession(): OpenRoleSession {
  if (typeof window === "undefined") return DEFAULT;
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return DEFAULT;
    return { ...DEFAULT, ...JSON.parse(raw) };
  } catch {
    return DEFAULT;
  }
}

export function saveSession(partial: Partial<OpenRoleSession>) {
  if (typeof window === "undefined") return;
  const next = { ...loadSession(), ...partial };
  localStorage.setItem(KEY, JSON.stringify(next));
}

export function sessionFromSearchParams(params: URLSearchParams): Partial<OpenRoleSession> {
  const jobId = params.get("job");
  const step = params.get("step");
  return {
    ...(jobId ? { jobId } : {}),
    ...(step ? { step } : {}),
  };
}
