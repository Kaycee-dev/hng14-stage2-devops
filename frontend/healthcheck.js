const http = require('http');

const port = parseInt(process.env.FRONTEND_PORT || '3000', 10);
const host = process.env.FRONTEND_HEALTH_HOST || '127.0.0.1';

const req = http.request(
  { host, port, path: '/health', method: 'GET', timeout: 2000 },
  (res) => {
    if (res.statusCode === 200) {
      process.exit(0);
    } else {
      process.exit(1);
    }
  },
);

req.on('error', () => process.exit(1));
req.on('timeout', () => {
  req.destroy();
  process.exit(1);
});

req.end();
