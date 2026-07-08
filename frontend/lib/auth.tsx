"use client";

// Globalny stan roli zalogowanego użytkownika (admin | user) — do sterowania UI.
// Wypełniany przez AuthGate po zalogowaniu; konsumowany przez nawigację i strony.
import { createContext, useContext } from "react";

export type AuthState = {
  role: string | null;
  username: string | null;
  authEnabled: boolean;
  isAdmin: boolean;
  logout: () => void;
};

export const AuthContext = createContext<AuthState>({
  role: null, username: null, authEnabled: true, isAdmin: false, logout: () => {},
});

export const useAuth = () => useContext(AuthContext);
