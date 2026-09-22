import { useState } from 'react';
import { ArrowRight, Eye, EyeOff } from 'lucide-react';
import { Button, Field } from '../../components/ui';
import styles from './SignIn.module.css';

const MIN_PASSWORD = 8;

/** The email-and-password form, in either its sign-in or create-account shape. */
export default function CredentialsForm({ mode, busy, error, onSubmit }) {
  const isRegister = mode === 'register';
  const [form, setForm] = useState({ name: '', email: '', password: '' });
  const [visible, setVisible] = useState(false);

  const set = (key) => (event) => setForm((current) => ({ ...current, [key]: event.target.value }));

  const submit = (event) => {
    event.preventDefault();
    onSubmit(
      isRegister
        ? { name: form.name.trim(), email: form.email.trim(), password: form.password }
        : { email: form.email.trim(), password: form.password }
    );
  };

  return (
    <form className={styles.form} onSubmit={submit}>
      {isRegister && (
        <Field
          label="Your name"
          name="name"
          autoComplete="name"
          placeholder="Meera Raghavan"
          value={form.name}
          onChange={set('name')}
          required
        />
      )}

      <Field
        label="Email"
        name="email"
        type="email"
        autoComplete="email"
        placeholder="you@example.com"
        value={form.email}
        onChange={set('email')}
        required
      />

      <Field
        label="Password"
        name="password"
        type={visible ? 'text' : 'password'}
        autoComplete={isRegister ? 'new-password' : 'current-password'}
        placeholder={isRegister ? `At least ${MIN_PASSWORD} characters` : '••••••••'}
        value={form.password}
        onChange={set('password')}
        minLength={isRegister ? MIN_PASSWORD : undefined}
        required
        hint={isRegister ? 'Stored only as a bcrypt hash — nobody can read it back.' : undefined}
        trailing={
          <button
            type="button"
            className={styles.reveal}
            onClick={() => setVisible((shown) => !shown)}
            aria-label={visible ? 'Hide password' : 'Show password'}
          >
            {visible ? <EyeOff size={15} aria-hidden="true" /> : <Eye size={15} aria-hidden="true" />}
          </button>
        }
      />

      {error && <p className={styles.error}>{error}</p>}

      <Button type="submit" className={styles.submit} disabled={busy}>
        {busy ? 'One moment…' : isRegister ? 'Create account' : 'Sign in'}
        <ArrowRight size={15} aria-hidden="true" />
      </Button>
    </form>
  );
}
