'use strict';

const http = require('http');
const fs = require('fs');
const path = require('path');
const { WebSocketServer } = require('ws');

const PORT = process.env.PORT || 3000;

// ---------------------------------------------------------------------------
// Salas. El servidor empareja y nada más: la partida vive en el televisor.
// ---------------------------------------------------------------------------
const rooms = new Map(); // code -> { tv, pads: [sock|null, sock|null] }

const ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ'; // sin I, O, 0, 1

function newCode() {
  let code;
  do {
    code = '';
    for (let i = 0; i < 4; i++) code += ALPHABET[Math.floor(Math.random() * ALPHABET.length)];
  } while (rooms.has(code));
  return code;
}

// ---------------------------------------------------------------------------
// Estáticos, tolerantes a que public/ se haya aplanado al subir el repo
// ---------------------------------------------------------------------------
const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8'
};

const ROOTS = [
  path.join(__dirname, 'public'),
  __dirname,
  path.join(process.cwd(), 'public'),
  process.cwd()
];

function findFile(name, done) {
  let i = 0;
  (function next() {
    if (i >= ROOTS.length) return done(null);
    const candidate = path.join(ROOTS[i++], name);
    fs.readFile(candidate, (err, data) => (err ? next() : done({ path: candidate, data })));
  })();
}

const server = http.createServer((req, res) => {
  let route = req.url.split('?')[0];
  if (route === '/') route = '/tv.html';
  if (route === '/pad') route = '/pad.html';

  if (route === '/_debug') {
    const report = ROOTS.map((r) => {
      let listing;
      try { listing = fs.readdirSync(r).filter((f) => f !== 'node_modules').join('  '); }
      catch (e) { listing = '(no existe)'; }
      return r + '\n  ' + listing;
    }).join('\n\n');
    res.writeHead(200, { 'Content-Type': 'text/plain; charset=utf-8' });
    res.end('__dirname: ' + __dirname + '\ncwd: ' + process.cwd() + '\n\n' + report + '\n');
    return;
  }

  const safe = path.normalize(route).replace(/^(\.\.[/\\])+/, '');
  findFile(safe, (found) => {
    if (!found) {
      res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
      res.end('No encuentro ' + safe + '. Abre /_debug para ver qué archivos hay.');
      return;
    }
    res.writeHead(200, {
      'Content-Type': MIME[path.extname(found.path)] || 'text/plain',
      'Cache-Control': 'no-store'
    });
    res.end(found.data);
  });
});

// ---------------------------------------------------------------------------
// Señalización
// ---------------------------------------------------------------------------
const wss = new WebSocketServer({ server });

function send(sock, obj) {
  if (sock && sock.readyState === 1) sock.send(JSON.stringify(obj));
}

wss.on('connection', (sock) => {
  sock.isAlive = true;
  sock.on('pong', () => { sock.isAlive = true; });

  sock.on('message', (raw) => {
    const text = raw.toString();
    const room = rooms.get(sock.code);

    // Ruta de respaldo por WebSocket. Solo se usa si WebRTC no conectó, así
    // que aquí la claridad importa más que ahorrar microsegundos.
    if (text.lastIndexOf('{"t":"r"', 0) === 0) {
      if (room && sock.role === 'pad' && room.tv) {
        let p;
        try { p = JSON.parse(text); } catch (e) { return; }
        p.p = sock.slot;
        send(room.tv, p);
      }
      return;
    }

    let msg;
    try { msg = JSON.parse(text); } catch (e) { return; }

    if (msg.t === 'host') {
      const code = newCode();
      sock.role = 'tv';
      sock.code = code;
      rooms.set(code, { tv: sock, pads: [null, null] });
      send(sock, { t: 'room', code });
      return;
    }

    if (msg.t === 'join') {
      const code = String(msg.code || '').toUpperCase();
      const target = rooms.get(code);
      if (!target) { send(sock, { t: 'error', reason: 'nocode' }); return; }

      const slot = target.pads[0] === null ? 0 : (target.pads[1] === null ? 1 : -1);
      if (slot === -1) { send(sock, { t: 'error', reason: 'full' }); return; }

      sock.role = 'pad';
      sock.code = code;
      sock.slot = slot;
      target.pads[slot] = sock;
      send(sock, { t: 'joined', slot });
      send(target.tv, { t: 'peer', slot });
      return;
    }

    // El TV mantiene una conexión WebRTC por mando, así que hay que dirigir.
    if (msg.t === 'signal') {
      if (!room) return;
      if (sock.role === 'pad') send(room.tv, { t: 'signal', slot: sock.slot, data: msg.data });
      else send(room.pads[msg.slot], { t: 'signal', slot: msg.slot, data: msg.data });
      return;
    }
  });

  sock.on('close', () => {
    const room = rooms.get(sock.code);
    if (!room) return;
    if (sock.role === 'tv') {
      room.pads.forEach((p) => send(p, { t: 'gone' }));
      rooms.delete(sock.code);
    } else {
      room.pads[sock.slot] = null;
      send(room.tv, { t: 'left', slot: sock.slot });
    }
  });
});

setInterval(() => {
  wss.clients.forEach((sock) => {
    if (sock.isAlive === false) return sock.terminate();
    sock.isAlive = false;
    sock.ping();
  });
}, 25000);

server.listen(PORT, () => console.log('Arcade escuchando en el puerto ' + PORT));
