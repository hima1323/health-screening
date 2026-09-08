import { Routes, Route } from 'react-router-dom';
import { PrimaryProvider } from './context/PrimaryContext';
import ScanHub from './pages/ScanHub';
import SessionReport from './pages/SessionReport';
import BiometricTimeline from './pages/BiometricTimeline';

export default function App() {
  return (
    <PrimaryProvider>
      <Routes>
        <Route path="/" element={<ScanHub />} />
        <Route path="/report" element={<SessionReport />} />
        <Route path="/timeline" element={<BiometricTimeline />} />
      </Routes>
    </PrimaryProvider>
  );
}
