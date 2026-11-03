const fs = require('fs');
const path = require('path');
const QRCode = require('qrcode');

/*
 * Printable QR codes for presenting the reasoning model: one PNG per demo sample file. Scanning one from the Scan Hub
 * ("Begin contactless scan") shows the triage result for that sample. The codes never expire (lib/stationCode.js).
 *
 *   npm run demo-qr [-- <output dir>]          (default: docs/demo-qr)
 */
const SAMPLE_DIR = path.join(__dirname, '..', '..', 'reasoning_model', 'demo_samples');
const OUT = path.resolve(process.argv[2] || path.join(__dirname, '..', '..', 'docs', 'demo-qr'));

const LEVELS = {
  URGENT: 'urgent',
  SEE_DOCTOR_SOON: 'see-doctor-soon',
  SELF_CARE: 'self-care',
};

async function main() {
  if (!fs.existsSync(SAMPLE_DIR)) {
    throw new Error('No demo samples: run python -m triage.demo_samples --build in reasoning_model/src first');
  }
  fs.mkdirSync(OUT, { recursive: true });
  const files = fs.readdirSync(SAMPLE_DIR).filter((f) => f.endsWith('.json')).sort();
  for (const file of files) {
    const sample = JSON.parse(fs.readFileSync(path.join(SAMPLE_DIR, file), 'utf8'));
    const slug = sample.title
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .split('-')
      .slice(0, 6)
      .join('-');
    const name = `${sample.id}${LEVELS[sample.reference_level] ? `-${LEVELS[sample.reference_level]}` : ''}-${slug}.png`;
    await QRCode.toFile(path.join(OUT, name), `AURA-DEMO:${sample.id}`, { width: 720, margin: 2, errorCorrectionLevel: 'M' });
    console.log(`${name}  ${sample.title}`);
  }
  console.log(`${files.length} QR codes in ${OUT}`);
}

main().catch((err) => {
  console.error(err.message);
  process.exit(1);
});
