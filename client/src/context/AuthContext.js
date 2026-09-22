import { createContext } from 'react';

/** Carries the signed-in patient; the provider lives in AuthProvider.jsx. */
export const AuthContext = createContext(null);
