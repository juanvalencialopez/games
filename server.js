'use strict';

const http = require('http');
const fs = require('fs');
const path = require('path');
const { WebSocketServer } = require('ws');

const PORT = process.env.PORT || 3000;

// ---------------------------------------------------------------------------
// Salas. Solo empareja peers, nunca ejecuta lógica de juego.
// ---------------------------------------------------------------------------
const rooms = new Map(); // code -> { tv, pad }

// Sin I, O, 0, 1: se confunden al leerlos en una pantalla a 3 metros.
const ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ';

function newCode() {
  let code;
  do {
    code = '';
    for (let i = 0; i < 4; i++) {
      code += ALPHABET[Math.floor(Math.random() * ALPHABET.length)];
    }
  } while (rooms.has(code));
  return code;
}

// ---------------------------------------------------------------------------
// Estáticos
// ---------------------------------------------------------------------------
const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8'
};

// Al subir los archivos a GitHub es fácil que public/ se aplane. En vez de
// exigir una estructura, buscamos el archivo donde pueda estar.
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
    fs.readFile(candidate, (err, data) => {
      if (err) return next();
      done({ path: candidate, data: data });
    });
  })();
}

const server = http.createServer((req, res) => {
  let route = req.url.split('?')[0];
  if (route === '/') route = '/tv.html';
  if (route === '/pad') route = '/pad.html';

  // Diagnóstico: qué archivos ve el servidor realmente.
  if (route === '/_debug') {
    const report = ROOTS.map((r) => {
      let listing;
      try { listing = fs.readdirSync(r).filter((f) => f !== 'node_modules'); }
      catch (e) { listing = '(no existe)'; }
      return r + '\n  ' + (Array.isArray(listing) ? listing.join('  ') : listing);
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
// Signaling
// ---------------------------------------------------------------------------
const wss = new WebSocketServer({ server });

function send(sock, obj) {
  if (sock && sock.readyState === 1) sock.send(JSON.stringify(obj));
}

function peerOf(sock) {
  const room = rooms.get(sock.code);
  if (!room) return null;
  return sock.role === 'tv' ? room.pad : room.tv;
}

wss.on('connection', (sock) => {
  sock.isAlive = true;
  sock.on('pong', () => { sock.isAlive = true; });

  sock.on('message', (raw) => {
    const text = raw.toString();

    // Ruta rápida: los paquetes de input se reenvían sin parsear JSON.
    // Es la ruta que estamos midiendo, así que no le añadimos trabajo.
    if (text.charCodeAt(0) === 123 && text.lastIndexOf('{"t":"r"', 0) === 0) {
      const peer = peerOf(sock);
      if (peer && peer.readyState === 1) peer.send(text);
      return;
    }

    let msg;
    try { msg = JSON.parse(text); } catch (e) { return; }

    if (msg.t === 'host') {
      const code = newCode();
      sock.role = 'tv';
      sock.code = code;
      rooms.set(code, { tv: sock, pad: null });
      send(sock, { t: 'room', code: code });
      return;
    }

    if (msg.t === 'join') {
      const code = String(msg.code || '').toUpperCase();
      const room = rooms.get(code);
      if (!room) { send(sock, { t: 'error', reason: 'nocode' }); return; }
      if (room.pad) { send(sock, { t: 'error', reason: 'full' }); return; }
      sock.role = 'pad';
      sock.code = code;
      room.pad = sock;
      send(room.tv, { t: 'peer' });
      send(sock, { t: 'peer' });
      return;
    }

    // Oferta / respuesta / candidatos ICE
    if (msg.t === 'signal') {
      const peer = peerOf(sock);
      send(peer, { t: 'signal', data: msg.data });
      return;
    }
  });

  sock.on('close', () => {
    const room = rooms.get(sock.code);
    if (!room) return;
    if (sock.role === 'tv') {
      send(room.pad, { t: 'gone' });
      rooms.delete(sock.code);
    } else {
      room.pad = null;
      send(room.tv, { t: 'gone' });
    }
  });
});

// Muchos hosts gratuitos cierran sockets inactivos a los 55 s.
setInterval(() => {
  wss.clients.forEach((sock) => {
    if (sock.isAlive === false) return sock.terminate();
    sock.isAlive = false;
    sock.ping();
  });
}, 25000);

server.listen(PORT, () => {
  console.log('Banco de pruebas escuchando en el puerto ' + PORT);
});
