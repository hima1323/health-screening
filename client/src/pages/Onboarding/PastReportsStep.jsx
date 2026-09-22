import { useState } from 'react';
import { ArrowLeft, ArrowRight, FolderUp } from 'lucide-react';
import { deletePastReport, uploadPastReports } from '../../api';
import useAuth from '../../hooks/useAuth';
import ReportUploader from '../../components/ReportUploader';
import { Button, Card, IconBadge } from '../../components/ui';
import styles from './Onboarding.module.css';

/** Step 3 of onboarding: bring along whatever the last clinic gave you. Optional. */
export default function PastReportsStep({ user, onFinish, onBack }) {
  const { applyUser } = useAuth();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const run = async (work) => {
    setBusy(true);
    setError(null);
    try {
      applyUser(await work);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const reports = user.pastReports || [];

  return (
    <Card className={styles.panel}>
      <div className={styles.heading}>
        <IconBadge tone="amber">
          <FolderUp size={18} strokeWidth={1.6} />
        </IconBadge>
        <div>
          <p className="label tight">Step 3 of 3</p>
          <h2 className={styles.title}>Bring your past reports</h2>
        </div>
      </div>

      <p className={styles.body}>
        Blood work, an old ECG, a discharge summary — anything from an earlier visit gives the station
        something to compare today&apos;s reading against. This step is optional and you can add more later.
      </p>

      <ReportUploader
        reports={reports}
        busy={busy}
        error={error}
        onUpload={(files) => run(uploadPastReports(files))}
        onRemove={(reportId) => run(deletePastReport(reportId))}
      />

      <div className={styles.actions}>
        <Button variant="link" onClick={onBack} disabled={busy}>
          <ArrowLeft size={15} aria-hidden="true" /> Back to details
        </Button>
        <Button className={styles.submit} onClick={onFinish} disabled={busy}>
          {reports.length ? 'Finish and open Scan Hub' : 'Skip for now'}
          <ArrowRight size={15} aria-hidden="true" />
        </Button>
      </div>
    </Card>
  );
}
