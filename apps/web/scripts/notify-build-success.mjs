import fs from 'node:fs/promises';

const url = process.env.BUILD_SUCCESS_URL;
const secret = process.env.BUILD_SECRET;
const manifestPath = process.env.DEPLOYMENT_MANIFEST_PATH || '.sinpes-deployment.json';

if (!url || !secret) {
  console.log('Build confirmation skipped: BUILD_SUCCESS_URL or BUILD_SECRET is not configured.');
  process.exit(0);
}

let manifest;
try {
  manifest = JSON.parse(await fs.readFile(manifestPath, 'utf8'));
} catch {
  console.log('Build confirmation skipped: deployment manifest was not captured for this build.');
  process.exit(0);
}

if (!manifest?.deployment_id) {
  throw new Error('Build confirmation blocked: deployment manifest is missing deployment_id.');
}

const response = await fetch(url, {
  method: 'POST',
  headers: {
    'content-type': 'application/json',
    'x-build-secret': secret,
    'x-deployment-id': manifest.deployment_id,
  },
  body: JSON.stringify({
    deployment_id: manifest.deployment_id,
    artifact_hash: manifest.artifact_hash || '',
  }),
});

if (!response.ok) {
  const detail = await response.text();
  throw new Error(`Build confirmation failed (${response.status}): ${detail.slice(0, 300)}`);
}

console.log(`Backend build lock confirmed and released for deployment ${manifest.deployment_id}.`);
