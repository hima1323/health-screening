import { useNavigate } from 'react-router-dom';
import { LogOut } from 'lucide-react';
import useAuth from '../../hooks/useAuth';
import styles from './AccountChip.module.css';

/** Who is signed in, and the way out. */
export default function AccountChip() {
  const { user, signOut } = useAuth();
  const navigate = useNavigate();

  if (!user) return null;

  const leave = () => {
    signOut();
    navigate('/welcome', { replace: true });
  };

  return (
    <div className={styles.chip}>
      <span className={styles.avatar} aria-hidden="true">
        {user.initials}
      </span>
      <span className={styles.identity}>
        <span className={styles.name}>{user.profile?.fullName || user.name}</span>
        <span className={styles.email}>{user.email}</span>
      </span>
      <button type="button" className={styles.signOut} onClick={leave} aria-label="Sign out">
        <LogOut size={15} aria-hidden="true" />
      </button>
    </div>
  );
}
