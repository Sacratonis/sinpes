const url = process.env.BUILD_SUCCESS_URL;
const secret = process.env.BUILD_SECRET;

if (!url || !secret) {
  console.log('Build confirmation skipped: BUILD_SUCCESS_URL or BUILD_SECRET is not configured.');
  process.exit(0);
}

const response = await fetch(url, {
  method: 'POST',
  headers: { 'x-build-secret': secret },
});

if (!response.ok) {
  const detail = await response.text();
  throw new Error(`Build confirmation failed (${response.status}): ${detail.slice(0, 300)}`);
}

console.log('Backend build lock confirmed and released.');
