// ===========================================================================
// Monedas: naves con inercia recogiendo monedas contra el reloj.
// El stick apunta, A empuja en esa dirección, B frena.
// ===========================================================================
(function () {
  'use strict';

  var DEAD = 0.16, TURN = 9.0, ACCEL = 1.25, DRAG = 0.62, BRAKE = 0.03;
  var VMAX = 0.85, R = 0.022, PR = 0.026;
  var ROUND = 60;      // segundos

  var ships, coins, left;

  function newShip(i) {
    return { x: i === 0 ? 0.3 : 0.7, y: 0.5, vx: 0, vy: 0, h: i === 0 ? 0 : Math.PI, score: 0 };
  }
  function spawn() { return { x: 0.08 + Math.random() * 0.84, y: 0.10 + Math.random() * 0.80 }; }

  function angleDiff(a, b) {
    var d = (a - b) % (Math.PI * 2);
    if (d > Math.PI) d -= Math.PI * 2;
    if (d < -Math.PI) d += Math.PI * 2;
    return d;
  }

  window.Arcade.register({
    id: 'coins',
    name: 'Monedas',
    hint: '1 o 2 jugadores · stick apunta, A empuja, B frena',

    init: function () {
      ships = [newShip(0), newShip(1)];
      coins = [];
      for (var i = 0; i < 5; i++) coins.push(spawn());
      left = ROUND;
    },

    step: function (dt, api) {
      left -= dt;
      if (left <= 0) {
        var win = -1, text = 'Se acabó el tiempo';
        if (api.joined[0] && api.joined[1]) {
          if (ships[0].score !== ships[1].score) {
            win = ships[0].score > ships[1].score ? 0 : 1;
            text = 'Gana el jugador ' + (win + 1);
          } else text = 'Empate';
        } else {
          var solo = api.joined[0] ? 0 : 1;
          text = ships[solo].score + ' monedas';
        }
        api.finish(text, win);
        return;
      }

      for (var i = 0; i < 2; i++) {
        if (!api.joined[i]) continue;
        var s = ships[i], p = api.pads[i];
        var sx = p ? p.x : 0, sy = p ? p.y : 0;
        var mag = Math.sqrt(sx * sx + sy * sy);

        if (mag > DEAD) {
          var target = Math.atan2(sy, sx);
          var turn = TURN * dt * Math.min(1, (mag - DEAD) / (1 - DEAD) + 0.35);
          var d = angleDiff(target, s.h);
          s.h += Math.abs(d) < turn ? d : (d > 0 ? turn : -turn);
          s.h = s.h % (Math.PI * 2);
        }

        if (p && p.a) { s.vx += Math.cos(s.h) * ACCEL * dt; s.vy += Math.sin(s.h) * ACCEL * dt; }

        var k = Math.pow(p && p.b ? BRAKE : DRAG, dt);
        s.vx *= k; s.vy *= k;

        var sp = Math.sqrt(s.vx * s.vx + s.vy * s.vy);
        if (sp > VMAX) { s.vx *= VMAX / sp; s.vy *= VMAX / sp; }

        s.x += s.vx * dt; s.y += s.vy * dt;

        if (s.x < R) { s.x = R; s.vx = Math.abs(s.vx) * 0.5; }
        if (s.x > 1 - R) { s.x = 1 - R; s.vx = -Math.abs(s.vx) * 0.5; }
        if (s.y < R) { s.y = R; s.vy = Math.abs(s.vy) * 0.5; }
        if (s.y > 1 - R) { s.y = 1 - R; s.vy = -Math.abs(s.vy) * 0.5; }

        for (var j = 0; j < coins.length; j++) {
          var dx = s.x - coins[j].x, dy = s.y - coins[j].y;
          if (Math.sqrt(dx * dx + dy * dy) < R + PR) { s.score++; coins[j] = spawn(); }
        }
      }
    },

    draw: function (cx, W, H, api) {
      var A = window.Arcade, S = Math.min(W, H);
      cx.fillStyle = A.BG;
      cx.fillRect(0, 0, W, H);
      cx.strokeStyle = A.EDGE;
      cx.lineWidth = Math.max(2, S * 0.004);
      cx.strokeRect(0, 0, W, H);

      for (var j = 0; j < coins.length; j++) {
        cx.fillStyle = A.MUTED;
        cx.beginPath();
        cx.arc(coins[j].x * W, coins[j].y * H, PR * S, 0, Math.PI * 2);
        cx.fill();
      }

      for (var i = 0; i < 2; i++) {
        if (!api.joined[i]) continue;
        var s = ships[i], p = api.pads[i];
        var x = s.x * W, y = s.y * H, r = R * S;

        if (p && p.a) {
          cx.fillStyle = 'rgba(230,234,247,0.45)';
          cx.beginPath();
          cx.moveTo(x - Math.cos(s.h) * r * 1.1 - Math.sin(s.h) * r * 0.45,
                    y - Math.sin(s.h) * r * 1.1 + Math.cos(s.h) * r * 0.45);
          cx.lineTo(x - Math.cos(s.h) * r * 2.3, y - Math.sin(s.h) * r * 2.3);
          cx.lineTo(x - Math.cos(s.h) * r * 1.1 + Math.sin(s.h) * r * 0.45,
                    y - Math.sin(s.h) * r * 1.1 - Math.cos(s.h) * r * 0.45);
          cx.fill();
        }

        cx.fillStyle = A.COLORS[i];
        cx.beginPath();
        cx.moveTo(x + Math.cos(s.h) * r * 1.5, y + Math.sin(s.h) * r * 1.5);
        cx.lineTo(x + Math.cos(s.h + 2.5) * r, y + Math.sin(s.h + 2.5) * r);
        cx.lineTo(x + Math.cos(s.h - 2.5) * r, y + Math.sin(s.h - 2.5) * r);
        cx.fill();

        if (p && p.b) {
          cx.strokeStyle = A.INK;
          cx.lineWidth = Math.max(2, S * 0.004);
          cx.beginPath();
          cx.arc(x, y, r * 1.9, 0, Math.PI * 2);
          cx.stroke();
        }
      }

      cx.textBaseline = 'top';
      cx.textAlign = 'left';
      var xs = W * 0.03;
      cx.font = '700 ' + Math.round(H * 0.08) + 'px "Courier New", monospace';
      for (var k = 0; k < 2; k++) {
        if (!api.joined[k]) continue;
        cx.fillStyle = A.COLORS[k];
        cx.fillText(ships[k].score, xs, H * 0.03);
        xs += W * 0.09;
      }

      cx.textAlign = 'center';
      cx.fillStyle = left < 10 ? A.WARN : A.MUTED;
      cx.font = '700 ' + Math.round(H * 0.06) + 'px "Courier New", monospace';
      cx.fillText(Math.max(0, left).toFixed(1), W / 2, H * 0.03);
    }
  });
})();
