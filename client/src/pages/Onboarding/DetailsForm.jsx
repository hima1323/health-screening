import { useState } from 'react';
import { ArrowRight, ClipboardList } from 'lucide-react';
import { saveProfile } from '../../api';
import useAuth from '../../hooks/useAuth';
import { Button, Card, Field, FieldRow, IconBadge } from '../../components/ui';
import styles from './Onboarding.module.css';

const SEXES = ['Female', 'Male', 'Intersex', 'Prefer not to say'];
const BLOOD_GROUPS = ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-', 'Unknown'];

/** Step 2 of onboarding: the details the screening station needs before it can read you. */
export default function DetailsForm({ user, onSaved }) {
  const { applyUser } = useAuth();
  const [form, setForm] = useState({
    fullName: user.profile?.fullName || user.name || '',
    age: user.profile?.age || '',
    sex: user.profile?.sex || '',
    phone: user.profile?.phone || '',
    heightCm: user.profile?.heightCm || '',
    weightKg: user.profile?.weightKg || '',
    bloodGroup: user.profile?.bloodGroup || '',
    conditions: user.profile?.conditions || '',
    medications: user.profile?.medications || '',
    consentAccepted: user.profile?.consentAccepted || false,
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const set = (key) => (event) =>
    setForm((current) => ({
      ...current,
      [key]: event.target.type === 'checkbox' ? event.target.checked : event.target.value,
    }));

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      applyUser(await saveProfile(form));
      onSaved();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card className={styles.panel}>
      <form className={styles.form} onSubmit={submit}>
        <div className={styles.heading}>
          <IconBadge tone="rose">
            <ClipboardList size={18} strokeWidth={1.6} />
          </IconBadge>
          <div>
            <p className="label tight">Step 2 of 3</p>
            <h2 className={styles.title}>Tell us about you</h2>
          </div>
        </div>

        <p className={styles.body}>
          The station reads your vitals against your own baseline, so age and build change how a result is
          scored. Everything here stays on your record.
        </p>

        <FieldRow>
          <Field
            label="Full name"
            name="fullName"
            autoComplete="name"
            value={form.fullName}
            onChange={set('fullName')}
            required
          />
          <Field
            label="Age"
            name="age"
            type="number"
            min="1"
            max="120"
            value={form.age}
            onChange={set('age')}
            required
          />
        </FieldRow>

        <FieldRow>
          <Field label="Sex" name="sex" as="select" value={form.sex} onChange={set('sex')}>
            <option value="">Select</option>
            {SEXES.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </Field>
          <Field
            label="Blood group"
            name="bloodGroup"
            as="select"
            value={form.bloodGroup}
            onChange={set('bloodGroup')}
          >
            <option value="">Select</option>
            {BLOOD_GROUPS.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </Field>
          <Field
            label="Phone"
            name="phone"
            type="tel"
            autoComplete="tel"
            placeholder="+91 98765 43210"
            value={form.phone}
            onChange={set('phone')}
          />
        </FieldRow>

        <FieldRow>
          <Field
            label="Height (cm)"
            name="heightCm"
            type="number"
            min="30"
            max="250"
            value={form.heightCm}
            onChange={set('heightCm')}
          />
          <Field
            label="Weight (kg)"
            name="weightKg"
            type="number"
            min="2"
            max="350"
            value={form.weightKg}
            onChange={set('weightKg')}
          />
        </FieldRow>

        <Field
          label="Ongoing conditions"
          name="conditions"
          as="textarea"
          placeholder="Asthma, hypertension, anything a clinician should know"
          value={form.conditions}
          onChange={set('conditions')}
          hint="Leave blank if there are none."
        />

        <Field
          label="Current medication"
          name="medications"
          as="textarea"
          placeholder="Name and dose, one per line"
          value={form.medications}
          onChange={set('medications')}
        />

        <label className={styles.consent}>
          <input
            type="checkbox"
            checked={form.consentAccepted}
            onChange={set('consentAccepted')}
            required
          />
          <span>
            I consent to contactless screening at an Aura Screen station, and to my readings being stored
            against this account until I withdraw consent.
          </span>
        </label>

        {error && <p className={styles.error}>{error}</p>}

        <Button type="submit" className={styles.submit} disabled={busy}>
          {busy ? 'Saving…' : 'Save and continue'}
          <ArrowRight size={15} aria-hidden="true" />
        </Button>
      </form>
    </Card>
  );
}
