const { mkdirSync, writeFileSync } = require('node:fs');

mkdirSync('reports', { recursive: true });
writeFileSync('reports/build.json', JSON.stringify({ built: true }));
