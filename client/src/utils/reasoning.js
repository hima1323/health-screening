/*
 * A report's reasoning-model call, for lists and badges. Live scans now run the triage expert system
 * (report.reasoning); reports from earlier live scans carry the stress model's output (report.model) instead.
 */
const LEVEL_WORDS = {
  URGENT: 'Urgent',
  SEE_DOCTOR_SOON: 'See a doctor soon',
  SELF_CARE: 'Self-care',
  REMEASURE: 'Remeasure',
  RETAKE: 'Retake',
  NOT_SUITABLE: 'Not suitable',
};

/** { title, urgent, review } for a report the model read, or null. */
export function modelCall(report) {
  if (report.reasoning) {
    const { level } = report.reasoning;
    return {
      title: LEVEL_WORDS[level] ?? report.reasoning.label,
      urgent: level === 'URGENT',
      review: level === 'SEE_DOCTOR_SOON' || level === 'REMEASURE',
    };
  }
  const summary = report.model?.summary;
  if (!summary) return null;
  if (summary.abstain) return { title: 'Unclear mental load', urgent: false, review: false };
  return { title: `${summary.label === 'high' ? 'High' : 'Low'} mental load`, urgent: false, review: summary.label === 'high' };
}
