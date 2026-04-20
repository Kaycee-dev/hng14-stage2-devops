const express = require('express');
const axios = require('axios');
const path = require('path');

const app = express();

const API_URL = process.env.FRONTEND_API_BASE_URL || 'http://api:8000';
const PORT = parseInt(process.env.FRONTEND_PORT || '3000', 10);
const HOST = process.env.FRONTEND_HOST || '0.0.0.0';

app.use(express.json());
app.use(express.static(path.join(__dirname, 'views')));

app.get('/health', async (req, res) => {
  try {
    const upstream = await axios.get(`${API_URL}/health`, { timeout: 2000 });
    if (upstream.status === 200) {
      return res.status(200).json({ status: 'ok', api: 'reachable' });
    }
    return res.status(503).json({ status: 'degraded', api: 'non_200' });
  } catch (err) {
    return res.status(503).json({ status: 'degraded', api: 'unreachable' });
  }
});

app.post('/submit', async (req, res) => {
  try {
    const response = await axios.post(`${API_URL}/jobs`, null, { timeout: 5000 });
    res.json(response.data);
  } catch (err) {
    res.status(502).json({ error: 'api_unreachable' });
  }
});

app.get('/status/:id', async (req, res) => {
  try {
    const response = await axios.get(`${API_URL}/jobs/${req.params.id}`, { timeout: 5000 });
    res.json(response.data);
  } catch (err) {
    if (err.response && err.response.status === 404) {
      return res.status(404).json({ error: 'not_found' });
    }
    res.status(502).json({ error: 'api_unreachable' });
  }
});

const server = app.listen(PORT, HOST, () => {
  console.log(`Frontend listening on ${HOST}:${PORT} -> ${API_URL}`);
});

function shutdown(signal) {
  console.log(`Received ${signal}, shutting down`);
  server.close(() => process.exit(0));
  setTimeout(() => process.exit(1), 10000).unref();
}

process.on('SIGTERM', () => shutdown('SIGTERM'));
process.on('SIGINT', () => shutdown('SIGINT'));
