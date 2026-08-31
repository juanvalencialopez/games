// ===========================================================================
// Asteroides: la nave se mueve libre y dispara hacia arriba.
// A dispara, B activa modo lento para apuntar fino.
// Perder las 3 vidas te saca; gana quien más puntos tenga al final.
// ===========================================================================
(function () {
  'use strict';

  var SPEED = 0.62, SLOW = 0.26;
  var FIRE_GAP = 0.16, BULLET_V = 1.25, BULLET_R = 0.008;
  var SHIP_R = 0.026;
  var ROUND = 90;
  var LIVES = 3;

  var ships, rocks, bullets, left, spawnGap, spawnAt;

  function newShip(i) {
    return { x: i === 0 ? 0.35 : 0.65, y: 0.86, score: 0, lives: LIVES, cool: 0, hurt: 0 };
  }

  function newRock() {
    var big = Math.random() < 0.35;
    return {
      x: 0.06 + Math.random() * 0.88,
      y: -0.06,
      vx: (Math.random() - 0.5) * 0.16,
      vy: 0.14 + Math.random() * 0.20,
      r: big ? 0.052 : 0.032,
      hp: big ? 2 : 1,
      spin: Math.random() * Math.PI,
      dspin: (Math.random() - 0.5) * 2.4
    };
  }

  window.Arcade.register({
    id: 'shooter',
    name: 'Asteroides',
    hint: '1 o 2 jugadores · stick mueve, A dispara, B apunta lento',

    init: function () {
      ships = [newShip(0), newShip(1)];
      rocks = [];
      bullets = [];
      left = ROUND;
      spawnGap = 1.1;
      spawnAt = 0.6;
    },

    step: function (dt, api) {
      left -= dt;

      // Aparición: se acelera con el tiempo, pero con piso para que no colapse.
      spawnAt -= dt;
      if (spawnAt <= 0) {
        rocks.push(newRock());
        spawnGap = Math.max(0.34, spawnGap * 0.975);
        spawnAt = spawnGap * (0.7 + Math.random() * 0.6);
      }

      var alive = 0;
      for (var i = 0; i < 2; i++) {
        if (!api.joined[i]) continue;
        var s = ships[i], p = api.pads[i];
        if (s.lives > 0) alive++;
        if (s.lives <= 0) continue;

        var v = (p && p.b) ? SLOW : SPEED;
        if (p) { s.x += p.x * v * dt; s.y += p.y * v * dt; }
        s.x = Math.max(SHIP_R, Math.min(1 - SHIP_R, s.x));
        s.y = Math.max(0.30, Math.min(1 - SHIP_R, s.y));

        s.cool -= dt;
        if (s.hurt > 0) s.hurt -= dt;
        if (p && p.a && s.cool <= 0) {
          bullets.push({ x: s.x, y: s.y - SHIP_R, owner: i });
          s.cool = FIRE_GAP;
        }
      }

      for (var b = bullets.length - 1; b >= 0; b--) {
        bullets[b].y -= BULLET_V * dt;
        if (bullets[b].y < -0.05) bullets.splice(b, 1);
      }

      for (var r = rocks.length - 1; r >= 0; r--) {
        var k = rocks[r];
        k.x += k.vx * dt; k.y += k.vy * dt; k.spin += k.dspin * dt;
        if (k.x < k.r || k.x > 1 - k.r) k.vx = -k.vx;
        if (k.y > 1.1) { rocks.splice(r, 1); continue; }

        var gone = false;
        for (var b2 = bullets.length - 1; b2 >= 0 && !gone; b2--) {
          var d = Math.sqrt(Math.pow(bullets[b2].x - k.x, 2) + Math.pow(bullets[b2].y - k.y, 2));
          if (d < k.r + BULLET_R) {
            var own = bullets[b2].owner;
            bullets.splice(b2, 1);
            k.hp--;
            if (k.hp <= 0) {
              ships[own].score += k.r > 0.04 ? 3 : 1;
              // Los grandes se parten en dos chicos, como corresponde.
              if (k.r > 0.04) {
                for (var f = 0; f < 2; f++) {
                  rocks.push({ x: k.x, y: k.y, vx: (f ? 1 : -1) * 0.22, vy: k.vy * 0.9,
                               r: 0.032, hp: 1, spin: 0, dspin: (Math.random() - 0.5) * 3 });
                }
              }
              rocks.splice(r, 1);
              gone = true;
            }
          }
        }
        if (gone) continue;

        for (var i2 = 0; i2 < 2; i2++) {
          if (!api.joined[i2]) continue;
          var s2 = ships[i2];
          if (s2.lives <= 0 || s2.hurt > 0) continue;
          var dd = Math.sqrt(Math.pow(s2.x - k.x, 2) + Math.pow(s2.y - k.y, 2));
          if (dd < k.r + SHIP_R) {
            s2.lives--;
            s2.hurt = 1.6;
            rocks.splice(r, 1);
            break;
          }
        }
      }

      var over = left <= 0 || alive === 0;
      if (over) {
        var win = -1, text;
        if (api.joined[0] && api.joined[1]) {
          if (ships[0].score !== ships[1].score) {
            win = ships[0].score > ships[1].score ? 0 : 1;
            text = 'Gana el jugador ' + (win + 1);
          } else text = 'Empate';
        } else {
          var solo = api.joined[0] ? 0 : 1;
          text = ships[solo].score + ' puntos';
        }
        api.finish(text, win);
      }
    },

    draw: function (cx, W, H, api) {
      var A = window.Arcade, S = Math.min(W, H);
      cx.fillStyle = A.BG;
      cx.fillRect(0, 0, W, H);

      for (var r = 0; r < rocks.length; r++) {
        var k = rocks[r];
        cx.save();
        cx.translate(k.x * W, k.y * H);
        cx.rotate(k.spin);
        cx.fillStyle = k.hp > 1 ? A.WARN : '#8B96C4';
        cx.beginPath();
        for (var v = 0; v < 7; v++) {
          var ang = (v / 7) * Math.PI * 2;
          var rad = k.r * S * (0.78 + 0.22 * Math.abs(Math.sin(v * 2.7)));
          if (v === 0) cx.moveTo(Math.cos(ang) * rad, Math.sin(ang) * rad);
          else cx.lineTo(Math.cos(ang) * rad, Math.sin(ang) * rad);
        }
        cx.closePath();
        cx.fill();
        cx.restore();
      }

      for (var b = 0; b < bullets.length; b++) {
        cx.fillStyle = A.COLORS[bullets[b].owner];
        cx.fillRect(bullets[b].x * W - S * 0.004, bullets[b].y * H - S * 0.016, S * 0.008, S * 0.032);
      }

      for (var i = 0; i < 2; i++) {
        if (!api.joined[i]) continue;
        var s = ships[i];
        if (s.lives <= 0) continue;
        if (s.hurt > 0 && Math.floor(s.hurt * 12) % 2 === 0) continue;
        var x = s.x * W, y = s.y * H, rr = SHIP_R * S;

        cx.fillStyle = A.COLORS[i];
        cx.beginPath();
        cx.moveTo(x, y - rr * 1.4);
        cx.lineTo(x + rr, y + rr * 0.9);
        cx.lineTo(x, y + rr * 0.4);
        cx.lineTo(x - rr, y + rr * 0.9);
        cx.closePath();
        cx.fill();

        if (api.pads[i] && api.pads[i].b) {
          cx.strokeStyle = A.INK;
          cx.lineWidth = Math.max(1, S * 0.003);
          cx.beginPath();
          cx.moveTo(x, y - rr * 1.4);
          cx.lineTo(x, 0);
          cx.stroke();
        }
      }

      cx.textBaseline = 'top';
      cx.textAlign = 'left';
      for (var q = 0; q < 2; q++) {
        if (!api.joined[q]) continue;
        var ty = H * 0.03 + q * H * 0.08;
        cx.fillStyle = A.COLORS[q];
        cx.font = '700 ' + Math.round(H * 0.055) + 'px "Courier New", monospace';
        cx.fillText(ships[q].score, W * 0.03, ty);
        for (var l = 0; l < ships[q].lives; l++) {
          cx.fillRect(W * 0.03 + W * 0.055 + l * S * 0.028, ty + H * 0.012, S * 0.018, S * 0.026);
        }
      }

      cx.textAlign = 'center';
      cx.fillStyle = left < 10 ? A.WARN : A.MUTED;
      cx.font = '700 ' + Math.round(H * 0.055) + 'px "Courier New", monospace';
      cx.fillText(Math.max(0, left).toFixed(1), W / 2, H * 0.03);
    }
  });
})();
