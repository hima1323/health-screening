import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, ChevronRight, Stethoscope, Trash2 } from 'lucide-react';
import { addDoctorNote, deleteDoctorNote, getDoctorNotes, getDoctorPatient } from '../../api';
import useResource from '../../hooks/useResource';
import usePageTitle from '../../hooks/usePageTitle';
import { formatDate } from '../../components/SessionCard';
import { Button, Card, CardRow, StatusPill, Spinner, ErrorState } from '../../components/ui';
import { rangePosition } from '../../utils/range';
import { RESULTS } from '../../utils/results';
import { SUMMARY_LABEL, initials, triage } from './doctor';
import styles from './DoctorPatient.module.css';
import { modelCall } from '../../utils/reasoning';

const POSITION_LABEL = { above: 'Above range', below: 'Below range', within: 'In range' };

/** One patient: where they stand now, how their readings moved across shared reports, the reports, and their screenings. */
export default function DoctorPatient() {
  const { patientId } = useParams();
  const { data, error } = useResource(() => getDoctorPatient(patientId), [patientId]);
  usePageTitle(data ? `${data.patient.name} · Clinician` : 'Patient · Clinician');

  if (error) return <ErrorState message={error} />;
  if (!data) return <Spinner />;

  const { patient, history } = data;
  const when = (r) => new Date(r.recordedAt ?? r.sharedAt).getTime();
  const reports = data.reports.map((r) => ({ ...r, triage: triage(r) })).sort((a, b) => when(b) - when(a));
  const latest = reports[0];
  const oldestFirst = [...reports].reverse();

  return (
    <>
      <div className={styles.head}>
        <Link to="/doctor/patients" className={styles.back}>
          <ArrowLeft size={14} aria-hidden="true" /> Patients
        </Link>
        <div className={styles.identity}>
          <span className={styles.avatar} aria-hidden="true">
            {initials(patient.name)}
          </span>
          <div className={styles.who}>
            <h1 className={styles.title}>{patient.name}</h1>
            <p className="muted small">
              {patient.age} years · {reports.length} shared report{reports.length === 1 ? '' : 's'} · latest{' '}
              {formatDate(latest.recordedAt)}
            </p>
          </div>
          <StatusPill dot={false}>{latest.triage.label}</StatusPill>
        </div>
      </div>

      {latest.nurseCheck?.queueId && (
        <Card accent="rose" className={styles.nurse}>
          <p className={styles.nurseTitle}>
            <Stethoscope size={16} aria-hidden="true" /> Nurse check requested on {formatDate(latest.recordedAt)} · queue #
            {latest.nurseCheck.queueId}
          </p>
          <p className="muted small">{latest.nurseCheck.message}</p>
        </Card>
      )}

      {/* where they stand now: the latest value of each measure against its range */}
      <section className={styles.latest} aria-label="Latest readings">
        {RESULTS.filter(({ key }) => latest[key]).map(({ key, label, unit, icon: Icon }) => {
          const r = latest[key];
          const position = rangePosition(r.value, r.normalRange)?.position;
          return (
            <Card key={key} className={styles.tile}>
              <div className={styles.tileTop}>
                <span className={styles.tileLabel}>{label}</span>
                <Icon size={16} strokeWidth={1.7} aria-hidden="true" />
              </div>
              <p className={`${styles.tileValue} ${position && position !== 'within' ? styles.out : ''}`.trim()}>
                {r.value}
                <small> {unit}</small>
              </p>
              <p className="muted small">
                Normal {r.normalRange ?? '—'} · <strong>{POSITION_LABEL[position] ?? r.status}</strong>
              </p>
            </Card>
          );
        })}
      </section>

      <div className={styles.columns}>
        <Card>
          <h3>Readings across shared reports</h3>
          <p className="muted small">Oldest to newest · out-of-range values in red</p>
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th scope="col">Measure</th>
                  {oldestFirst.map((r) => (
                    <th key={r.shareCode} scope="col">
                      {formatDate(r.recordedAt)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {RESULTS.filter(({ key }) => reports.some((r) => r[key])).map(({ key, label, unit }) => (
                  <tr key={key}>
                    <th scope="row">{label}</th>
                    {oldestFirst.map((r) => {
                      const v = r[key];
                      const position = v && rangePosition(v.value, v.normalRange)?.position;
                      return (
                        <td key={r.shareCode} className={position && position !== 'within' ? styles.out : ''}>
                          {v ? (
                            <>
                              {v.value} <small>{unit}</small>
                            </>
                          ) : (
                            '—'
                          )}
                        </td>
                      );
                    })}
                  </tr>
                ))}
                {reports.some(modelCall) && (
                  <tr>
                    <th scope="row">Reasoning model</th>
                    {oldestFirst.map((r) => {
                      const call = modelCall(r);
                      return (
                        <td key={r.shareCode} className={call?.urgent || call?.review ? styles.out : ''}>
                          {call?.title ?? '—'}
                        </td>
                      );
                    })}
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </Card>

        <Card>
          <h3>Shared reports</h3>
          <ul className={styles.list}>
            {reports.map((r) => (
              <li key={r.shareCode}>
                <Link to={`/doctor/reports/${r.shareCode}`} className={styles.row}>
                  <div className={styles.rowMain}>
                    <p className={styles.rowTitle}>
                      {formatDate(r.recordedAt)} · Session {r.sessionId}
                    </p>
                    <p className="muted small">
                      {r.triage.outOfRange.length > 0
                        ? `Out of range: ${r.triage.outOfRange.map((x) => x.label.toLowerCase()).join(', ')}`
                        : 'All readings in range'}
                      {modelCall(r) && ` · model: ${modelCall(r).title}`} · shared {formatDate(r.sharedAt)}
                    </p>
                  </div>
                  <StatusPill dot={false}>{r.triage.label}</StatusPill>
                  <ChevronRight size={16} className={styles.chevron} aria-hidden="true" />
                </Link>
              </li>
            ))}
          </ul>
        </Card>
      </div>

      {data.sessions?.length > 0 && (
        <Card>
          <h3>Recorded sessions</h3>
          <p className="muted small">Each opens into what the model concluded and all the original data</p>
          <ul className={styles.list}>
            {data.sessions.map((s) => (
              <li key={s.sessionKey}>
                <Link to={`/doctor/patients/${patientId}/sessions/${s.sessionKey}`} className={styles.row}>
                  <div className={styles.rowMain}>
                    <p className={styles.rowTitle}>
                      {s.label} · {s.source.dataset}
                    </p>
                    <p className="muted small">{s.summary?.text}</p>
                  </div>
                  <StatusPill dot={false}>{SUMMARY_LABEL[s.summary?.status] ?? 'No summary'}</StatusPill>
                  <ChevronRight size={16} className={styles.chevron} aria-hidden="true" />
                </Link>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Notes patientId={patientId} />

      <Card>
        <h3>Screening history</h3>
        {history.length === 0 ? (
          <p className="muted small">No screenings recorded.</p>
        ) : (
          <ul className={styles.list}>
            {history.map((log) => (
              <li key={log._id} className={styles.historyItem}>
                <CardRow>
                  <div>
                    <p className={styles.rowTitle}>{log.dateLabel}</p>
                    <p className="muted small">
                      {log.type} · {log.location}
                    </p>
                  </div>
                  <StatusPill dot={false}>{log.status}</StatusPill>
                </CardRow>
                <p className={styles.vitals}>
                  Heart rate <strong>{log.heartRate ?? '—'} bpm</strong>
                  {log.temp != null && (
                    <>
                      {' '}
                      · Temperature <strong>{log.temp} °C</strong>
                    </>
                  )}
                </p>
                {log.clinicianDirective && <p className="muted small">{log.clinicianDirective}</p>}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </>
  );
}

/** The doctor's own notes on this patient — private to them, newest first. */
function Notes({ patientId }) {
  const [notes, setNotes] = useState(null);
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    getDoctorNotes(patientId).then(({ notes: list }) => setNotes(list), (err) => setError(err.message));
  }, [patientId]);

  async function add(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const { note } = await addDoctorNote(patientId, text);
      setNotes((list) => [note, ...list]);
      setText('');
    } catch (err) {
      setError(err.message);
    }
    setBusy(false);
  }

  async function remove(id) {
    try {
      await deleteDoctorNote(id);
      setNotes((list) => list.filter((n) => n._id !== id));
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <Card>
      <h3>Your notes</h3>
      <p className="muted small">Only you see these.</p>
      <form className={styles.noteForm} onSubmit={add}>
        <textarea
          className={styles.noteInput}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="e.g. Fever on today's scan — ask about sore throat and fluids."
          maxLength={2000}
          rows={3}
          aria-label="New note"
        />
        <Button type="submit" className={styles.noteSubmit} disabled={busy || !text.trim()}>
          {busy ? 'Saving…' : 'Add note'}
        </Button>
      </form>
      {error && (
        <p className="muted small" role="alert">
          {error}
        </p>
      )}
      {notes?.length > 0 && (
        <ul className={styles.list}>
          {notes.map((note) => (
            <li key={note._id} className={styles.note}>
              <div>
                <p className={styles.noteText}>{note.text}</p>
                <p className="muted small">{formatDate(note.createdAt)}</p>
              </div>
              <button type="button" className={styles.noteDelete} onClick={() => remove(note._id)} aria-label="Delete note">
                <Trash2 size={15} aria-hidden="true" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
