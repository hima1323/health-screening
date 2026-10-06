import { HeartPulse, Thermometer, Wind } from 'lucide-react';

/** The key results, in the order a patient reads them, with what each one measures. */
export const RESULTS = [
  { key: 'heartRate', label: 'Heart rate', unit: 'bpm', icon: HeartPulse, tone: 'rose', measures: 'How many times your heart beats in a minute.' },
  { key: 'bodyTemp', label: 'Body temperature', unit: '°C', icon: Thermometer, tone: 'amber', measures: 'How warm your body is inside.' },
  { key: 'respiration', label: 'Breathing rate', unit: '/min', icon: Wind, tone: undefined, measures: 'How many breaths you take in a minute.' },
];
