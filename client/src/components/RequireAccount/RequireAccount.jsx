import { Navigate, Outlet } from 'react-router-dom';
import useAuth from '../../hooks/useAuth';
import { PrimaryProvider } from '../../context/PrimaryProvider';

/**
 * Guards the screening screens: an unknown visitor meets the introduction, and a
 * signed-in patient who has not filled in their details finishes onboarding first.
 */
export default function RequireAccount() {
  const { user } = useAuth();

  if (!user) return <Navigate to="/welcome" replace />;
  if (!user.profileComplete) return <Navigate to="/onboarding" replace />;

  return (
    <PrimaryProvider>
      <Outlet />
    </PrimaryProvider>
  );
}
