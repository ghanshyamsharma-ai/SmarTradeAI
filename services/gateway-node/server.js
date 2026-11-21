import http from 'node:http';
import cors from 'cors';
import express from 'express';
import { createProxyMiddleware } from 'http-proxy-middleware';

const port = Number(process.env.PORT || 3000);
const coreApi = process.env.CORE_API_URL || 'http://127.0.0.1:8000';

const app = express();
app.use(cors());

app.get('/health', (_req, res) => {
  res.json({ status: 'ok', service: 'node-express-gateway', coreApi });
});

const proxy = createProxyMiddleware({
  target: coreApi,
  changeOrigin: true,
  ws: true,
  logLevel: 'warn',
});

app.use('/api', proxy);
app.use('/ws', proxy);
app.use(proxy);

const server = http.createServer(app);
server.on('upgrade', (req, socket, head) => proxy.upgrade(req, socket, head));
server.listen(port, () => console.log(`Express gateway listening on :${port}`));
