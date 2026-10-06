import { useEffect, useState } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { getDoctorMe, getDoctorToken, setDoctorToken } from '../../api';
import { Spinner } from '../../components/ui';
import DoctorShell from './DoctorShell';

/**
 * Guards the doctor pages: no doctor session → the doctor sign-in.
 * Signed in, the pages render inside the dashboard shell.
 */
export default function RequireDoctor() {
  const location = useLocation();
  const navigate = useNavigate();
  const [doctor, setDoctor] = useState(null);
  const [failed, setFailed] = useState(false);
  const hasToken = Boolean(getDoctorToken());

  useEffect(() => {
    if (!hasToken) return;
    let active = true;
    getDoctorMe().then(
      ({ doctor: me }) => active && setDoctor(me),
      () => active && setFailed(true)
    );
    return () => {
      active = false;
    };
  }, [hasToken]);

  if (!hasToken || failed) return <Navigate to="/doctor/login" replace state={{ from: location.pathname }} />;
  if (!doctor) return <Spinner />;

  const signOut = () => {
    setDoctorToken(null);
    navigate('/doctor/login', { replace: true });
  };
  return <DoctorShell doctor={doctor} signOut={signOut} />;
}
