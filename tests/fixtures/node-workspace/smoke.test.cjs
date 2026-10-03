const assert = require('node:assert/strict');
const { readFileSync, writeFileSync } = require('node:fs');
const { resolve } = require('node:path');
const { test } = require('node:test');

test('default commands run in the nested npm workspace after build', () => {
  assert.equal(process.env.CI, 'true');
  assert.equal(JSON.parse(readFileSync('package.json')).name, 'actions-node-smoke-web');
  assert.equal(JSON.parse(readFileSync('reports/build.json')).built, true);
  assert.equal(JSON.parse(readFileSync('../../package-lock.json')).lockfileVersion, 3);
  assert.match(process.env.npm_config_user_agent, /^npm\/\d+\.\d+\.\d+ /);
  // The downloaded evidence verifier checks the configured Node/npm versions.
  writeFileSync('reports/runtime.json', JSON.stringify({
    node: process.versions.node,
    npm: process.env.npm_config_user_agent.split(' ')[0].slice(4),
    workdir: process.cwd(),
    lockfile: resolve('../../package-lock.json'),
  }));
});
