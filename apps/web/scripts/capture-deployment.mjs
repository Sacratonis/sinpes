import fs from 'node:fs/promises';

const manifestUrl = process.env.DEPLOYMENT_MANIFEST_URL;
const outputPath = process.env.DEPLOYMENT_MANIFEST_PATH || '.sinpes-deployment.json';

if (!manifestUrl) {
  await fs.rm(outputPath, { force: true });
  console.log('Deployment manifest capture skipped: DEPLOYMENT_MANIFEST_URL is not configured.');
  process.exit(0);
}

const response = await fetch(manifestUrl, { cache: 'no-store' });
if (!response.ok) {
  throw new Error(`Deployment manifest fetch failed (${response.status})`);
}

const manifest = await response.json();
if (!manifest || typeof manifest.deployment_id !== 'string' || !manifest.deployment_id) {
  throw new Error('Deployment manifest is missing deployment_id.');
}

await fs.writeFile(outputPath, `${JSON.stringify(manifest)}\n`, 'utf8');
console.log(`Captured deployment manifest ${manifest.deployment_id}.`);
