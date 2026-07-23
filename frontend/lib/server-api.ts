import "server-only";

import type { Session } from "next-auth";

import { tokenForSession } from "@/lib/internal-auth";
import type { CurrentUser } from "@/types";


const API_BASE_URL = process.env.API_BASE_URL || "http://127.0.0.1:8000";

export async function getCurrentUser(session: Session): Promise<CurrentUser | null> {
  try {
    const token = await tokenForSession(session);
    const response = await fetch(`${API_BASE_URL}/me`, {
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "application/json",
      },
      cache: "no-store",
    });
    if (!response.ok) return null;
    return response.json() as Promise<CurrentUser>;
  } catch {
    return null;
  }
}
