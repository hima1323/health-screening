import { Navigate, Outlet } from 'react-router-dom';
import useAuth from '../../hooks/useAuth';

/** Keeps a fully onboarded patient out of the introduction and sign-in screens. */
export default function RequireGuest() {
  const { user } = useAuth();

  if (user?.profileComplete) return <Navigate to="/" replace />;

  return <Outlet />;
}
