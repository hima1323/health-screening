import { useContext } from 'react';
import { AuthContext } from '../context/AuthContext';

/** The signed-in patient plus the sign-in, sign-up and sign-out actions. */
export default function useAuth() {
  return useContext(AuthContext);
}
