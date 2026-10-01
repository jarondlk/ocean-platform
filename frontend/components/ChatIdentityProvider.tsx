"use client";
import { createContext, useContext, type ReactNode } from "react";
const ChatIdentity = createContext<string | null>(null);
export function ChatIdentityProvider({ accountId, children }: { accountId: string; children: ReactNode }) {
  return <ChatIdentity.Provider value={accountId}>{children}</ChatIdentity.Provider>;
}
export function useChatIdentity() { return useContext(ChatIdentity); }
