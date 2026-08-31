// ===========================================================================
// Ruta: carrera con perspectiva. No es 3D real; es la técnica de Out Run.
// La pista son tramos que se proyectan con perspectiva y se dibujan como
// trapecios, así que un televisor lento la mueve sin despeinarse.
//
// stick izquierda/derecha dobla, A acelera, B frena.
// ===========================================================================
(function () {
  'use strict';

  var SEG = 200;           // largo de cada tramo
  var ROAD_W = 2200;       // media anchura de la pista
  var CAM_H = 1100;        // altura de la cámara
  var CAM_DEPTH = 0.84;    // ~100 grados de campo visual
  var CAM_BACK = 600;      // cuánto va la cámara por detrás del líder
  var DRAW_N = 220;        // tramos dibujados hacia adelante

  var VMAX = 9000, ACCEL = 4200, BRAKE = 9500, DRAG = 1800;
  var OFF_DRAG = 3000, OFF_VMAX = 3200;
  var STEER = 1.9, CENTRIF = 0.32;
  var SPIN_TIME = 1.0;

  var TRACK_SEGS = 800;
  var FINISH_Z;

  var segments, obstacles, cars, elapsed;

  // -------------------------------------------------------------------------
  // Pista. Generada con semilla fija para que ambos corran exactamente la misma.
  // -------------------------------------------------------------------------
  function buildTrack() {
    var s = 987654321;
    function rnd() { s = (s * 1103515245 + 12345) & 0x7fffffff; return s / 0x7fffffff; }

    segments = [];
    var curve = 0, targetCurve = 0, hold = 0;
    var hill = 0, targetHill = 0, holdH = 0;

    for (var i = 0; i < TRACK_SEGS; i++) {
      if (hold-- <= 0) {
        targetCurve = i < 40 ? 0 : (rnd() - 0.5) * 5.2;
        if (rnd() < 0.35) targetCurve = 0;          // rectas de descanso
        hold = 30 + Math.floor(rnd() * 60);
      }
      if (holdH-- <= 0) {
        targetHill = i < 40 ? 0 : (rnd() - 0.5) * 2400;
        holdH = 40 + Math.floor(rnd() * 70);
      }
      curve += (targetCurve - curve) * 0.06;
      hill  += (targetHill  - hill)  * 0.05;

      segments.push({
        index: i,
        curve: curve,
        y1: hill * (i / TRACK_SEGS),
        color: Math.floor(i / 3) % 2 === 0
      });
    }
    // Altura acumulada de cada tramo
    var acc = 0;
    for (var j = 0; j < segments.length; j++) {
      acc += segments[j].y1 * 0.02;
      segments[j].y = acc;
    }

    FINISH_Z = (TRACK_SEGS - 6) * SEG;

    obstacles = [];
    var y = 90;
    while (y < TRACK_SEGS - 40) {
      var n = rnd() < 0.32 ? 2 : 1;
      var used = [];
      for (var k = 0; k < n; k++) {
        var x, t = 0, ok;
        do {
          x = -0.72 + rnd() * 1.44;
          ok = true;
          for (var u = 0; u < used.length; u++) if (Math.abs(used[u] - x) < 0.7) ok = false;
          t++;
        } while (!ok && t < 8);
        used.push(x);
        obstacles.push({ seg: Math.floor(y), x: x, hit: [false, false] });
      }
      y += 22 + rnd() * 26;
    }
  }

  function newCar(i) {
    return { z: 0, x: i === 0 ? -0.35 : 0.35, v: 0, spin: 0, hits: 0, finished: 0 };
  }

  function segAt(z) {
    var i = Math.floor(z / SEG);
    return segments[Math.max(0, Math.min(segments.length - 1, i))];
  }

  window.Arcade.register({
    id: 'racer3d',
    name: 'Ruta',
    hint: '1 o 2 jugadores · stick dobla, A acelera, B frena',

    init: function () {
      buildTrack();
      cars = [newCar(0), newCar(1)];
      elapsed = 0;
    },

    step: function (dt, api) {
      elapsed += dt;

      var leadZ = 0;
      for (var q = 0; q < 2; q++) if (api.joined[q] && cars[q].z > leadZ) leadZ = cars[q].z;
      var camZ = leadZ - CAM_BACK;

      for (var i = 0; i < 2; i++) {
        if (!api.joined[i]) continue;
        var c = cars[i], p = api.pads[i];
        if (c.finished) continue;

        var off = Math.abs(c.x) > 1;
        var pct = c.v / VMAX;

        if (c.spin > 0) {
          c.spin -= dt;
          c.v -= DRAG * 2.2 * dt;
        } else {
          if (p && p.a) c.v += ACCEL * dt;
          if (p && p.b) c.v -= BRAKE * dt;
          if (!p || (!p.a && !p.b)) c.v -= DRAG * dt;
          if (off) c.v -= OFF_DRAG * dt;
          if (p) c.x += p.x * STEER * pct * dt;
        }

        // Fuerza centrífuga: en curva te empuja hacia afuera, y más rápido vas
        // más te empuja. Es lo que obliga a soltar el acelerador.
        c.x -= segAt(c.z).curve * pct * CENTRIF * dt;

        var top = off ? OFF_VMAX : VMAX;
        if (c.v > top) c.v = top;
        if (c.v < 0) c.v = 0;
        c.x = Math.max(-1.9, Math.min(1.9, c.x));
        c.z += c.v * dt;

        var segIdx = Math.floor(c.z / SEG);
        for (var j = 0; j < obstacles.length; j++) {
          var o = obstacles[j];
          if (o.hit[i]) continue;
          if (Math.abs(o.seg - segIdx) > 1) continue;
          if (Math.abs(o.x - c.x) > 0.42) continue;
          o.hit[i] = true;
          c.hits++;
          c.spin = SPIN_TIME;
          c.v *= 0.28;
        }

        // Quedarse atrás te devuelve al plano de cámara, igual que en 2D.
        if (c.z < camZ) { c.z = camZ; c.v *= 0.55; }

        if (c.z >= FINISH_Z && !c.finished) {
          c.finished = elapsed;
          var text, win = i;
          if (api.joined[0] && api.joined[1]) text = 'Gana el jugador ' + (i + 1);
          else { text = elapsed.toFixed(1) + ' s'; win = -1; }
          api.finish(text, win);
        }
      }
    },

    draw: function (cx, W, H, api) {
      var A = window.Arcade;

      var leadZ = 0, leader = 0;
      for (var q = 0; q < 2; q++) if (api.joined[q] && cars[q].z > leadZ) { leadZ = cars[q].z; leader = q; }
      var camZ = leadZ - CAM_BACK;
      var camX = cars[leader].x * ROAD_W;
      var camY = segAt(leadZ).y + CAM_H;

      // Cielo y pasto
      cx.fillStyle = '#16224A';
      cx.fillRect(0, 0, W, H);
      cx.fillStyle = '#101B26';
      cx.fillRect(0, H * 0.5, W, H * 0.5);

      var base = Math.floor(camZ / SEG);
      var x = 0, dx = 0, maxy = H;
      var sprites = [];

      // Recorremos de cerca a lejos y recortamos con maxy: así una cuesta tapa
      // lo que hay detrás, que es lo que da la sensación de relieve.
      var prev = null;
      for (var n = 0; n < DRAW_N; n++) {
        var idx = base + n;
        if (idx < 0 || idx >= segments.length) break;
        var seg = segments[idx];

        var zNear = idx * SEG, zFar = (idx + 1) * SEG;
        var p1 = proj(x, seg.y, zNear);
        var p2 = proj(x + dx, segments[Math.min(idx + 1, segments.length - 1)].y, zFar);

        // Guardamos aquí el desplazamiento acumulado de curva. Si no, cada
        // objeto tendría que recalcularlo desde cero y el coste se dispara.
        seg._x = x;
        x += dx;
        dx += seg.curve;

        if (!p1 || !p2) { prev = null; continue; }
        if (p1.y <= p2.y || p2.y >= maxy) { prev = p1; continue; }

        // Asfalto
        quad(p1.x - p1.w, p1.y, p1.x + p1.w, p1.y, p2.x + p2.w, p2.y, p2.x - p2.w, p2.y,
             seg.color ? '#182150' : '#1B2559');
        // Bermas
        var rw1 = p1.w * 0.14, rw2 = p2.w * 0.14;
        var rc = seg.color ? '#2C3873' : '#FF6B7A';
        quad(p1.x - p1.w - rw1, p1.y, p1.x - p1.w, p1.y, p2.x - p2.w, p2.y, p2.x - p2.w - rw2, p2.y, rc);
        quad(p1.x + p1.w, p1.y, p1.x + p1.w + rw1, p1.y, p2.x + p2.w + rw2, p2.y, p2.x + p2.w, p2.y, rc);
        // Línea central
        if (seg.color) {
          quad(p1.x - p1.w * 0.02, p1.y, p1.x + p1.w * 0.02, p1.y,
               p2.x + p2.w * 0.02, p2.y, p2.x - p2.w * 0.02, p2.y, '#2C3873');
        }
        // Meta
        if (idx === segments.length - 6) {
          quad(p1.x - p1.w, p1.y, p1.x + p1.w, p1.y, p2.x + p2.w, p2.y, p2.x - p2.w, p2.y, '#E6EAF7');
        }

        maxy = p1.y;
        prev = p1;
      }

      // Objetos: se juntan durante el recorrido y se pintan de lejos a cerca.
      for (var o = 0; o < obstacles.length; o++) {
        var ob = obstacles[o];
        if (ob.seg < base || ob.seg > base + DRAW_N) continue;
        var pp = projAt(ob.seg, ob.x);
        if (pp) sprites.push({ p: pp, kind: 'cone' });
      }
      for (var c2 = 0; c2 < 2; c2++) {
        if (!api.joined[c2]) continue;
        var pc = projCar(cars[c2]);
        if (pc) sprites.push({ p: pc, kind: 'car', i: c2, spin: cars[c2].spin, brake: api.pads[c2] && api.pads[c2].b });
      }
      sprites.sort(function (a, b) { return a.p.scale - b.p.scale; });

      for (var s = 0; s < sprites.length; s++) {
        var sp = sprites[s], P = sp.p;
        if (sp.kind === 'cone') {
          var cw = P.w * 0.16, ch = cw * 1.8;
          cx.fillStyle = '#FF6B7A';
          cx.beginPath();
          cx.moveTo(P.x, P.y - ch);
          cx.lineTo(P.x + cw, P.y);
          cx.lineTo(P.x - cw, P.y);
          cx.fill();
        } else {
          if (sp.spin > 0 && Math.floor(sp.spin * 12) % 2 === 0) continue;
          var vw = P.w * 0.44, vh = vw * 0.62;
          cx.fillStyle = A.COLORS[sp.i];
          cx.fillRect(P.x - vw / 2, P.y - vh, vw, vh);
          cx.fillStyle = 'rgba(14,22,51,0.55)';
          cx.fillRect(P.x - vw * 0.3, P.y - vh * 0.85, vw * 0.6, vh * 0.45);
          if (sp.brake) {
            cx.fillStyle = '#FF6B7A';
            cx.fillRect(P.x - vw / 2, P.y - vh * 0.22, vw, vh * 0.22);
          }
        }
      }

      hud(cx, W, H, api);

      // ---- helpers de proyección ----
      function proj(worldX, worldY, worldZ) {
        var dz = worldZ - camZ;
        if (dz < 30) return null;
        var scale = CAM_DEPTH / dz;
        return {
          x: W / 2 + scale * (worldX - camX) * W / 2,
          y: H / 2 - scale * (worldY - camY) * H / 2,
          w: scale * ROAD_W * W / 2,
          scale: scale
        };
      }

      function projAt(segIdx, offX) {
        var seg = segments[Math.min(segIdx, segments.length - 1)];
        if (seg._x === undefined) return null;   // tramo no dibujado este cuadro
        return proj(seg._x + offX * ROAD_W, seg.y, segIdx * SEG);
      }

      function projCar(car) {
        var segIdx = Math.floor(car.z / SEG);
        if (segIdx < base) return null;
        var seg = segments[Math.min(segIdx, segments.length - 1)];
        if (seg._x === undefined) return null;
        return proj(seg._x + car.x * ROAD_W, segAt(car.z).y, car.z);
      }

      function quad(x1, y1, x2, y2, x3, y3, x4, y4, color) {
        cx.fillStyle = color;
        cx.beginPath();
        cx.moveTo(x1, y1); cx.lineTo(x2, y2); cx.lineTo(x3, y3); cx.lineTo(x4, y4);
        cx.closePath();
        cx.fill();
      }
    }
  });

  function hud(cx, W, H, api) {
    var A = window.Arcade;
    cx.textBaseline = 'top';
    cx.textAlign = 'right';
    for (var k = 0; k < 2; k++) {
      if (!api.joined[k]) continue;
      var ty = H * 0.03 + k * H * 0.085;
      cx.fillStyle = A.COLORS[k];
      cx.font = '700 ' + Math.round(H * 0.058) + 'px "Courier New", monospace';
      cx.fillText(Math.round(cars[k].v / 45) + ' km/h', W * 0.97, ty);
      cx.fillStyle = A.MUTED;
      cx.font = '400 ' + Math.round(H * 0.024) + 'px "Courier New", monospace';
      cx.fillText('J' + (k + 1) + '  golpes ' + cars[k].hits + '   ' +
                  Math.round(100 * cars[k].z / FINISH_Z) + '%', W * 0.97, ty + H * 0.062);
    }
    cx.textAlign = 'center';
    cx.fillStyle = A.MUTED;
    cx.font = '400 ' + Math.round(H * 0.032) + 'px "Courier New", monospace';
    cx.fillText(elapsed.toFixed(1) + ' s', W / 2, H * 0.03);
  }
})();
