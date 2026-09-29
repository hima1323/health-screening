import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { Maximize2, Smartphone, Tablet } from 'lucide-react';
import styles from './DeviceFrame.module.css';

/*
 * Aura Screen is a phone / kiosk app. On a real device it fills the screen; on
 * a desktop it renders inside a device-sized frame so it can be demoed without
 * browser dev tools. The frame is a CSS size container, so every component
 * lays itself out against the device (`@container`, `cqw`/`cqh`), never the
 * browser window.
 */

// `bezel` is the margin DeviceFrame.module.css keeps around each frame
const DEVICES = {
  phone: { label: 'Phone', icon: Smartphone, width: 390, height: 844, bezel: 12 },
  kiosk: { label: 'Kiosk', icon: Tablet, width: 834, height: 1112, bezel: 20 },
  full: { label: 'Full screen', icon: Maximize2 },
};

const STORAGE_KEY = 'aura.device';
// stage padding, plus the picker and its gap above the frame
const STAGE_PAD_X = 48;
const STAGE_PAD_Y = 40 + 38 + 16;

function readStored() {
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

/** Phones and portrait kiosk displays are the real target — no frame there. */
function prefersFullScreen() {
  return window.innerWidth < 700 || window.innerHeight > window.innerWidth;
}

/** ?device=phone|kiosk|full wins, then the last choice, then a guess from the screen. */
function initialDevice() {
  const fromUrl = new URLSearchParams(window.location.search).get('device');
  if (fromUrl in DEVICES) return fromUrl;
  if (prefersFullScreen()) return 'full';
  const stored = readStored();
  return stored in DEVICES ? stored : 'phone';
}

// below this the text in a shrunken frame stops being readable
const MIN_SCALE = 0.85;

/**
 * How far to shrink the frame to fit the window. Fitting a tall frame into a
 * short window would shrink everything, so past MIN_SCALE only the width is
 * fitted and the page scrolls instead.
 */
function fitScale(device) {
  const spec = DEVICES[device];
  if (!spec.width) return 1;
  const sx = (window.innerWidth - STAGE_PAD_X - 2 * spec.bezel) / spec.width;
  const sy = (window.innerHeight - STAGE_PAD_Y - 2 * spec.bezel) / spec.height;
  const fit = Math.min(1, sx, sy);
  return fit >= MIN_SCALE ? fit : Math.min(1, sx);
}

export default function DeviceFrame({ children }) {
  const [device, setDevice] = useState(initialDevice);
  const [scale, setScale] = useState(() => fitScale(device));
  const screenRef = useRef(null);
  const { pathname } = useLocation();

  useLayoutEffect(() => {
    const onResize = () => setScale(fitScale(device));
    onResize();
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, [device]);

  // the screen scrolls, not the window, so a new route has to reset it by hand
  useEffect(() => {
    screenRef.current?.scrollTo(0, 0);
  }, [pathname]);

  const choose = (next) => {
    setDevice(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // private mode — the choice just won't be remembered
    }
  };

  // a window too narrow for the chosen frame gets the app at full size instead
  const shown = device !== 'full' && scale < MIN_SCALE ? 'full' : device;
  const spec = DEVICES[shown];
  const framed = shown !== 'full';
  // full screen on a desktop still needs a way back to the frame
  const showSwitcher = framed || !prefersFullScreen();

  return (
    <div className={styles.stage} data-device={shown}>
      {showSwitcher && (
        <div className={styles.switcher} role="group" aria-label="Preview device">
          {Object.entries(DEVICES).map(([key, d]) => (
            <button
              key={key}
              type="button"
              className={`${styles.option} ${key === device ? styles.optionActive : ''}`.trim()}
              aria-pressed={key === device}
              onClick={() => choose(key)}
            >
              <d.icon size={14} strokeWidth={1.8} />
              <span className={styles.optionLabel}>{d.label}</span>
            </button>
          ))}
          {framed && (
            <span className={styles.size}>
              {spec.width} × {spec.height}
            </span>
          )}
        </div>
      )}

      {/* reserves the scaled frame's on-screen footprint so it centres properly */}
      <div
        className={styles.footprint}
        style={framed ? { width: spec.width * scale, height: spec.height * scale } : undefined}
      >
        <div
          className={styles.device}
          style={
            framed
              ? { width: spec.width, height: spec.height, transform: `scale(${scale})` }
              : undefined
          }
        >
          <div ref={screenRef} className={styles.screen}>
            {children}
          </div>
        </div>
      </div>
    </div>
  );
}
