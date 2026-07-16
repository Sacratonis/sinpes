import { readFile } from 'node:fs/promises';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const fixturePath = path.join(root, 'tests', 'fixtures', 'blog-snapshot.json');
const fixture = await readFile(fixturePath);
const fixtureUrl = `data:application/json,${encodeURIComponent(fixture.toString('utf8'))}`;

const child = spawn(
  process.platform === 'win32' ? 'npm.cmd' : 'npm',
  ['run', 'build'],
  {
    cwd: root,
    stdio: 'inherit',
    env: {
      ...process.env,
      BLOG_SNAPSHOT_PRESIGNED_URL: fixtureUrl,
      BUILD_SUCCESS_URL: '',
      BUILD_SECRET: '',
    },
  },
);

const [exitCode, signal] = await once(child, 'close');
if (signal) process.kill(process.pid, signal);
process.exitCode = exitCode ?? 1;
