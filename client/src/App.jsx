import { Navigate, Route, Routes } from 'react-router-dom';
import './App.css';
import { AuthProvider } from './context/AuthProvider';
import DeviceFrame from './components/DeviceFrame';
import RequireAccount from './components/RequireAccount';
import RequireGuest from './components/RequireGuest';
import Welcome from './pages/Welcome';
import SignIn from './pages/SignIn';
import Onboarding from './pages/Onboarding';
import ScanHub from './pages/ScanHub';
import SessionReport from './pages/SessionReport';
import BiometricTimeline from './pages/BiometricTimeline';
import SessionAnalysis from './pages/SessionAnalysis';
import Kiosk from './pages/Kiosk';
import { DoctorLogin, DoctorOverview, DoctorPatient, DoctorPatients, DoctorReport, RequireDoctor } from './pages/Doctor';

export default function App() {
  return (
    <AuthProvider>
      {/* the phone / kiosk screen every page renders into */}
      <DeviceFrame>
        <Routes>
          {/* introduction and sign-in — hidden once the patient is fully onboarded */}
          <Route element={<RequireGuest />}>
            <Route path="/welcome" element={<Welcome />} />
            <Route path="/signin" element={<SignIn />} />
          </Route>

          {/* reachable while onboarding and afterwards, to attach more reports */}
          <Route path="/onboarding" element={<Onboarding />} />

          {/* the station's own screen — shows the signed QR code, needs no account */}
          <Route path="/kiosk" element={<Kiosk />} />

          {/* the clinician side — its own sign-in; a doctor sees only reports patients shared with them */}
          <Route path="/doctor/login" element={<DoctorLogin />} />
          <Route element={<RequireDoctor />}>
            <Route path="/doctor" element={<DoctorOverview />} />
            <Route path="/doctor/patients" element={<DoctorPatients />} />
            <Route path="/doctor/patients/:patientId" element={<DoctorPatient />} />
            <Route path="/doctor/reports/:code" element={<DoctorReport />} />
          </Route>

          {/* the screening app itself */}
          <Route element={<RequireAccount />}>
            <Route path="/" element={<ScanHub />} />
            <Route path="/report" element={<SessionReport />} />
            <Route path="/timeline" element={<BiometricTimeline />} />
            <Route path="/timeline/:key" element={<SessionAnalysis />} />
          </Route>

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </DeviceFrame>
    </AuthProvider>
  );
}
