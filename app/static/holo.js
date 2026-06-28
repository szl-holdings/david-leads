/* ============================================================================
 * holo.js — David Leads · Holographic 3D Visualization Module
 * © 2026 SZL Holdings · Apache-2.0
 * Self-contained. Pure Three.js (r128 globals via window.THREE). No external data.
 * Exposes a single global: window.Holo
 * ----------------------------------------------------------------------------
 * Visual identity: navy #0a2540 · gold #c08f2f · teal #168f89
 * Buckets: HOT #c0392b · WARM #c08f2f · NURTURE #5a6b7c
 * ============================================================================
 *
 * ─── SELF-TEST / USAGE EXAMPLE ───────────────────────────────────────────────
 * Each function returns a handle: { dispose(), resize(), el } so you can clean
 * up before re-render. Call dispose() on the previous handle (Holo also tracks
 * the last handle per container automatically and disposes it on re-init).
 *
 *   <div id="holoConstellation" style="height:420px"></div>
 *   <div id="holoGlobe"         style="height:420px"></div>
 *   <div id="holoPipe"          style="height:300px"></div>
 *
 *   const SAMPLE_LEADS = [
 *     { id:"L1", name:"New-parent household (NY metro)", score:91.2, bucket:"HOT",
 *       product:"Term / Whole Life (Family Coverage)", est_premium:3200,
 *       axes:{life_event_strength:.95,income_fit:.75,age_window_fit:.85,product_propensity:.9,recency:.9},
 *       moments:[{source:"CDC Natality",label:"Birth uptick"},{source:"BLS Wages",label:"Earnings rising"},{source:"Census ACS",label:"Family-formation band"}],
 *       nba:{action:"Call within 24h",talk_track:"New baby changes everything."} },
 *     { id:"L2", name:"Recently-promoted professional", score:84.0, bucket:"HOT",
 *       est_premium:4100, axes:{life_event_strength:.85,income_fit:.85,age_window_fit:.8,product_propensity:.8,recency:.85},
 *       moments:[{source:"SEC EDGAR 8-K",label:"Comp change"},{source:"BLS Wages",label:"Wage growth"},{source:"Census ACS",label:"Prime-earner band"}] },
 *     { id:"L3", name:"Mid-career dual-income family", score:78.5, bucket:"WARM",
 *       est_premium:5200, axes:{life_event_strength:.7,income_fit:.9,age_window_fit:.9,product_propensity:.85,recency:.6},
 *       moments:[{source:"Census ACS",label:"35–50 window"},{source:"BLS Wages",label:"Peak-earning"}] },
 *     { id:"L6", name:"Parent of college-age dependents", score:55.0, bucket:"NURTURE",
 *       est_premium:2400, axes:{life_event_strength:.6,income_fit:.75,age_window_fit:.65,product_propensity:.7,recency:.5},
 *       moments:[{source:"Census ACS",label:"College-age HH"},{source:"BLS Wages",label:"Tuition window"}] },
 *   ];
 *   const c = Holo.leadConstellation("holoConstellation", SAMPLE_LEADS);
 *
 *   const SAMPLE_AREAS = [
 *     { name:"New York County, New York", index:88, median_income:99000, median_age:37 },
 *     { name:"Westchester County, New York", index:74, median_income:103000, median_age:41 },
 *     { name:"Kings County, New York", index:69, median_income:67000, median_age:35 },
 *     { name:"Nassau County, New York", index:81, median_income:121000, median_age:42 },
 *     { name:"Suffolk County, New York", index:63, median_income:110000, median_age:43 },
 *   ];
 *   const g = Holo.territoryGlobe("holoGlobe", SAMPLE_AREAS);
 *
 *   const SAMPLE_PIPE = { HOT: 7300, WARM: 5200, NURTURE: 2400 };
 *   const p = Holo.pipeline3D("holoPipe", SAMPLE_PIPE);
 *
 *   // cleanup: c.dispose(); g.dispose(); p.dispose();
 * ─────────────────────────────────────────────────────────────────────────────
 */
(function (global) {
  "use strict";
  var THREE = global.THREE;

  /* ---------- brand palette ---------- */
  var COL = {
    navy: 0x0a2540, navy700: 0x143a5e, navy800: 0x0d2c4a,
    gold: 0xc08f2f, gold300: 0xd7b96b,
    teal: 0x168f89, teal300: 0x5cc4bf,
    hot: 0xc0392b, warm: 0xc08f2f, nurture: 0x5a6b7c
  };
  var BUCKET_COLOR = { HOT: COL.hot, WARM: COL.warm, NURTURE: COL.nurture };

  /* ---------- per-container handle registry (auto-dispose on re-init) ---------- */
  var REGISTRY = {};

  function disposeExisting(id) {
    if (REGISTRY[id] && typeof REGISTRY[id].dispose === "function") {
      try { REGISTRY[id].dispose(); } catch (e) { /* noop */ }
    }
    delete REGISTRY[id];
  }

  /* ---------- shared scene scaffold ---------- */
  function makeStage(containerId, opts) {
    opts = opts || {};
    var el = typeof containerId === "string" ? document.getElementById(containerId) : containerId;
    if (!el) { console.warn("[Holo] container not found:", containerId); return null; }
    if (!THREE) { console.warn("[Holo] THREE not loaded"); return null; }

    var w = el.clientWidth || 600, h = el.clientHeight || 400;

    var renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(w, h);
    renderer.setPixelRatio(Math.min(global.devicePixelRatio || 1, 2));
    renderer.domElement.style.display = "block";
    renderer.domElement.style.width = "100%";
    renderer.domElement.style.height = "100%";
    el.appendChild(renderer.domElement);

    var scene = new THREE.Scene();
    var cam = new THREE.PerspectiveCamera(opts.fov || 55, w / h, 0.1, 1000);
    cam.position.set(opts.camX || 0, opts.camY || 0, opts.camZ || 14);
    if (opts.lookAt) cam.lookAt(opts.lookAt);

    /* tooltip element */
    var tip = document.createElement("div");
    tip.className = "holo-tip";
    tip.style.display = "none";
    el.appendChild(tip);

    /* scanline + grid overlays (CSS-driven; toggled by holo.css classes) */
    var scan = document.createElement("div");
    scan.className = "holo-scanlines";
    el.appendChild(scan);

    return {
      el: el, renderer: renderer, scene: scene, cam: cam, tip: tip, scan: scan,
      w: w, h: h, disposables: []
    };
  }

  /* ---------- bloom-ish glow sprite (cheap radial gradient, no postprocessing) ---------- */
  var _glowTex = null;
  function glowTexture() {
    if (_glowTex) return _glowTex;
    var c = document.createElement("canvas");
    c.width = c.height = 128;
    var ctx = c.getContext("2d");
    var g = ctx.createRadialGradient(64, 64, 0, 64, 64, 64);
    g.addColorStop(0.0, "rgba(255,255,255,1)");
    g.addColorStop(0.2, "rgba(255,255,255,0.55)");
    g.addColorStop(0.5, "rgba(255,255,255,0.18)");
    g.addColorStop(1.0, "rgba(255,255,255,0)");
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, 128, 128);
    _glowTex = new THREE.CanvasTexture(c);
    return _glowTex;
  }

  /* ---------- ambient particle field (capped) ---------- */
  function ambientParticles(scene, count, spread, color, disposables) {
    count = Math.min(count || 220, 400);
    var geo = new THREE.BufferGeometry();
    var pos = new Float32Array(count * 3);
    for (var i = 0; i < count; i++) {
      pos[i * 3] = (Math.random() - 0.5) * spread;
      pos[i * 3 + 1] = (Math.random() - 0.5) * spread;
      pos[i * 3 + 2] = (Math.random() - 0.5) * spread;
    }
    geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    var mat = new THREE.PointsMaterial({
      color: color, size: 0.06, transparent: true, opacity: 0.5,
      depthWrite: false, blending: THREE.AdditiveBlending
    });
    var pts = new THREE.Points(geo, mat);
    scene.add(pts);
    disposables.push(geo, mat);
    return pts;
  }

  /* ---------- offscreen-aware RAF loop with cleanup ---------- */
  function runLoop(stage, step, extraDispose) {
    var rafId = null, running = true, paused = false;

    var io = null;
    if (global.IntersectionObserver) {
      io = new IntersectionObserver(function (entries) {
        paused = !entries[0].isIntersecting;
      }, { threshold: 0.01 });
      io.observe(stage.el);
    }

    var clock = new THREE.Clock();
    function frame() {
      if (!running) return;
      rafId = requestAnimationFrame(frame);
      if (paused || document.hidden) return;
      var dt = clock.getDelta(), t = clock.getElapsedTime();
      step(dt, t);
      stage.renderer.render(stage.scene, stage.cam);
    }
    frame();

    function resize() {
      var w = stage.el.clientWidth || stage.w, h = stage.el.clientHeight || stage.h;
      if (!w || !h) return;
      stage.w = w; stage.h = h;
      stage.renderer.setSize(w, h);
      stage.cam.aspect = w / h;
      stage.cam.updateProjectionMatrix();
    }
    var onResize = function () { resize(); };
    global.addEventListener("resize", onResize);

    function dispose() {
      running = false;
      if (rafId) cancelAnimationFrame(rafId);
      global.removeEventListener("resize", onResize);
      if (io) io.disconnect();
      // dispose tracked geometries/materials/textures
      (stage.disposables || []).forEach(function (d) {
        if (d && typeof d.dispose === "function") { try { d.dispose(); } catch (e) {} }
      });
      // walk the scene and dispose anything left
      stage.scene.traverse(function (o) {
        if (o.geometry && o.geometry.dispose) try { o.geometry.dispose(); } catch (e) {}
        if (o.material) {
          var mats = Array.isArray(o.material) ? o.material : [o.material];
          mats.forEach(function (m) {
            if (m.map && m.map.dispose) try { m.map.dispose(); } catch (e) {}
            if (m.dispose) try { m.dispose(); } catch (e) {}
          });
        }
      });
      if (typeof extraDispose === "function") { try { extraDispose(); } catch (e) {} }
      try { stage.renderer.dispose(); } catch (e) {}
      var dom = stage.renderer.domElement;
      if (dom && dom.parentNode) dom.parentNode.removeChild(dom);
      if (stage.tip && stage.tip.parentNode) stage.tip.parentNode.removeChild(stage.tip);
      if (stage.scan && stage.scan.parentNode) stage.scan.parentNode.removeChild(stage.scan);
    }

    return { dispose: dispose, resize: resize, el: stage.el, scene: stage.scene, cam: stage.cam };
  }

  function positionTip(stage, clientX, clientY, html) {
    var rect = stage.el.getBoundingClientRect();
    stage.tip.innerHTML = html;
    stage.tip.style.display = "block";
    var x = clientX - rect.left + 14, y = clientY - rect.top + 14;
    // keep inside container
    x = Math.min(x, stage.el.clientWidth - stage.tip.offsetWidth - 6);
    y = Math.min(y, stage.el.clientHeight - stage.tip.offsetHeight - 6);
    stage.tip.style.left = Math.max(4, x) + "px";
    stage.tip.style.top = Math.max(4, y) + "px";
  }

  function hideTip(stage) { stage.tip.style.display = "none"; }

  function money(n) { return "$" + Number(n || 0).toLocaleString(); }

  /* ===========================================================================
   * 1) LEAD CONSTELLATION
   * Glowing 3D node cloud. node = lead, size ∝ score, color by bucket,
   * links between leads sharing a moment.source. Auto-rotate + hover raycaster.
   * ========================================================================= */
  function leadConstellation(containerId, leads) {
    disposeExisting(containerId);
    var stage = makeStage(containerId, { fov: 55, camZ: 16 });
    if (!stage) return { dispose: function () {}, resize: function () {} };
    leads = (leads || []).slice();

    stage.scene.fog = new THREE.FogExp2(0x071a2e, 0.022);
    ambientParticles(stage.scene, 200, 34, COL.teal300, stage.disposables);

    var root = new THREE.Group();
    stage.scene.add(root);

    /* lay nodes on a fibonacci-ish sphere so they spread evenly */
    var N = leads.length, nodes = [];
    var glow = glowTexture();
    var maxScore = 1;
    leads.forEach(function (l) { maxScore = Math.max(maxScore, +l.score || 0); });

    var nodeGeoCache = {}; // share geometry by quantized radius
    function nodeGeo(r) {
      var key = r.toFixed(2);
      if (!nodeGeoCache[key]) { nodeGeoCache[key] = new THREE.SphereGeometry(r, 18, 18); stage.disposables.push(nodeGeoCache[key]); }
      return nodeGeoCache[key];
    }

    var R = 8;
    for (var i = 0; i < N; i++) {
      var l = leads[i];
      var y = N > 1 ? 1 - (i / (N - 1)) * 2 : 0;          // -1..1
      var radAtY = Math.sqrt(Math.max(0, 1 - y * y));
      var theta = i * 2.399963; // golden angle
      var px = Math.cos(theta) * radAtY * R;
      var pz = Math.sin(theta) * radAtY * R;
      var py = y * R * 0.72;

      var sc = (+l.score || 0) / 100;
      var radius = 0.28 + sc * 0.78;                       // size ∝ score
      var color = BUCKET_COLOR[l.bucket] || COL.teal;

      var coreMat = new THREE.MeshBasicMaterial({ color: color });
      var core = new THREE.Mesh(nodeGeo(radius), coreMat);
      core.position.set(px, py, pz);
      stage.disposables.push(coreMat);

      // wireframe accent shell
      var wireMat = new THREE.MeshBasicMaterial({ color: color, wireframe: true, transparent: true, opacity: 0.28 });
      var wire = new THREE.Mesh(nodeGeo(radius * 1.35), wireMat);
      wire.position.copy(core.position);
      stage.disposables.push(wireMat);

      // glow sprite
      var spriteMat = new THREE.SpriteMaterial({ map: glow, color: color, transparent: true, opacity: 0.7, depthWrite: false, blending: THREE.AdditiveBlending });
      var sprite = new THREE.Sprite(spriteMat);
      sprite.scale.setScalar(radius * 5.2);
      sprite.position.copy(core.position);
      stage.disposables.push(spriteMat);

      root.add(core); root.add(wire); root.add(sprite);
      core.userData = { lead: l, baseScale: 1, sprite: sprite, wire: wire, phase: Math.random() * 6.28 };
      nodes.push(core);
    }

    /* links between leads sharing a moment source */
    var linePts = [];
    function sourcesOf(l) {
      return (l.moments || []).map(function (m) { return (m.source || "").trim(); }).filter(Boolean);
    }
    for (var a = 0; a < N; a++) {
      var sa = sourcesOf(leads[a]);
      for (var b = a + 1; b < N; b++) {
        var sb = sourcesOf(leads[b]);
        var shared = sa.some(function (s) { return sb.indexOf(s) !== -1; });
        if (shared) {
          var pa = nodes[a].position, pb = nodes[b].position;
          linePts.push(pa.x, pa.y, pa.z, pb.x, pb.y, pb.z);
        }
      }
    }
    if (linePts.length) {
      var lgeo = new THREE.BufferGeometry();
      lgeo.setAttribute("position", new THREE.Float32BufferAttribute(linePts, 3));
      var lmat = new THREE.LineBasicMaterial({ color: COL.teal300, transparent: true, opacity: 0.22, blending: THREE.AdditiveBlending });
      var links = new THREE.LineSegments(lgeo, lmat);
      root.add(links);
      stage.disposables.push(lgeo, lmat);
    }

    /* hover raycaster */
    var ray = new THREE.Raycaster();
    var mouse = new THREE.Vector2();
    var hovered = null, lastClientX = 0, lastClientY = 0, autoRotate = true;

    function onMove(ev) {
      var rect = stage.el.getBoundingClientRect();
      lastClientX = ev.clientX; lastClientY = ev.clientY;
      mouse.x = ((ev.clientX - rect.left) / rect.width) * 2 - 1;
      mouse.y = -((ev.clientY - rect.top) / rect.height) * 2 + 1;
      ray.setFromCamera(mouse, stage.cam);
      var hits = ray.intersectObjects(nodes, false);
      if (hits.length) {
        var l = hits[0].object.userData.lead;
        hovered = hits[0].object;
        autoRotate = false;
        var html = '<div class="ht-name">' + escapeHtml(l.name) + '</div>' +
          '<div class="ht-row"><span class="ht-badge ' + l.bucket + '">' + l.bucket + '</span>' +
          '<span class="ht-score">' + (l.score) + '</span></div>' +
          (l.product ? '<div class="ht-meta">' + escapeHtml(l.product) + '</div>' : '') +
          (l.est_premium ? '<div class="ht-meta">~' + money(l.est_premium) + '/yr est.</div>' : '');
        positionTip(stage, ev.clientX, ev.clientY, html);
        stage.el.style.cursor = "pointer";
      } else {
        hovered = null; autoRotate = true; hideTip(stage); stage.el.style.cursor = "default";
      }
    }
    function onLeave() { hovered = null; autoRotate = true; hideTip(stage); stage.el.style.cursor = "default"; }
    stage.el.addEventListener("mousemove", onMove);
    stage.el.addEventListener("mouseleave", onLeave);

    var handle = runLoop(stage, function (dt, t) {
      if (autoRotate) root.rotation.y += dt * 0.22;
      root.rotation.x = Math.sin(t * 0.25) * 0.12;
      // pulse nodes (hovered pulses brighter/larger)
      for (var k = 0; k < nodes.length; k++) {
        var n = nodes[k], ph = n.userData.phase;
        var pulse = 1 + 0.12 * Math.sin(t * 2 + ph);
        var hi = (n === hovered) ? 1.45 : 1;
        n.scale.setScalar(pulse * hi);
        n.userData.sprite.material.opacity = (n === hovered ? 0.95 : 0.6) + 0.15 * Math.sin(t * 2 + ph);
        n.userData.wire.rotation.y += dt * 0.4;
      }
    }, function () {
      stage.el.removeEventListener("mousemove", onMove);
      stage.el.removeEventListener("mouseleave", onLeave);
    });

    REGISTRY[containerId] = handle;
    return handle;
  }

  /* ===========================================================================
   * 2) TERRITORY GLOBE — extruded bars (height ∝ index) over a stylized grid.
   * teal gradient, labels on hover.
   * ========================================================================= */
  function territoryGlobe(containerId, areas) {
    disposeExisting(containerId);
    var stage = makeStage(containerId, { fov: 52, camX: 0, camY: 16, camZ: 22, lookAt: new THREE.Vector3(0, 1.5, 0) });
    if (!stage) return { dispose: function () {}, resize: function () {} };
    areas = (areas || []).slice();

    stage.scene.fog = new THREE.FogExp2(0x071a2e, 0.018);
    ambientParticles(stage.scene, 160, 40, COL.teal300, stage.disposables);

    var root = new THREE.Group();
    stage.scene.add(root);

    /* glowing grid plane */
    var gridSpan = 18;
    var grid = new THREE.GridHelper(gridSpan, 18, COL.teal, COL.navy700);
    grid.material.transparent = true; grid.material.opacity = 0.35;
    root.add(grid);
    stage.disposables.push(grid.geometry, grid.material);

    // subtle dark base plane
    var planeGeo = new THREE.PlaneGeometry(gridSpan, gridSpan);
    var planeMat = new THREE.MeshBasicMaterial({ color: 0x07223a, transparent: true, opacity: 0.55 });
    var plane = new THREE.Mesh(planeGeo, planeMat);
    plane.rotation.x = -Math.PI / 2; plane.position.y = -0.02;
    root.add(plane);
    stage.disposables.push(planeGeo, planeMat);

    /* layout bars on a grid */
    var n = areas.length;
    var cols = Math.max(1, Math.ceil(Math.sqrt(n)));
    var rows = Math.max(1, Math.ceil(n / cols));
    var cell = gridSpan / (Math.max(cols, rows) + 1);
    var maxIdx = 1;
    areas.forEach(function (a) { maxIdx = Math.max(maxIdx, +a.index || 0); });

    var bars = [];
    var barGeo = new THREE.BoxGeometry(cell * 0.55, 1, cell * 0.55);
    stage.disposables.push(barGeo);

    function tealGrad(t) {
      // navy -> teal -> teal300 by height fraction t
      var c0 = new THREE.Color(COL.navy700), c1 = new THREE.Color(COL.teal), c2 = new THREE.Color(COL.teal300);
      var c = t < 0.5 ? c0.lerp(c1, t / 0.5) : c1.lerp(c2, (t - 0.5) / 0.5);
      return c;
    }

    for (var i = 0; i < n; i++) {
      var a = areas[i];
      var r = Math.floor(i / cols), cc = i % cols;
      var x = (cc - (cols - 1) / 2) * cell * 1.7;
      var z = (r - (rows - 1) / 2) * cell * 1.7;
      var frac = (+a.index || 0) / maxIdx;
      var height = 0.5 + frac * 4.5;
      var col = tealGrad(frac);

      var mat = new THREE.MeshBasicMaterial({ color: col, transparent: true, opacity: 0.92 });
      var bar = new THREE.Mesh(barGeo, mat);
      bar.scale.y = height;
      bar.position.set(x, height / 2, z);
      stage.disposables.push(mat);

      // wireframe halo
      var wmat = new THREE.MeshBasicMaterial({ color: COL.teal300, wireframe: true, transparent: true, opacity: 0.3 });
      var wire = new THREE.Mesh(barGeo, wmat);
      wire.scale.set(1.08, height * 1.01, 1.08);
      wire.position.copy(bar.position);
      stage.disposables.push(wmat);

      root.add(bar); root.add(wire);
      bar.userData = { area: a, baseH: height };
      bars.push(bar);
    }

    /* hover raycaster */
    var ray = new THREE.Raycaster();
    var mouse = new THREE.Vector2();
    var hovered = null, autoRotate = true;

    function onMove(ev) {
      var rect = stage.el.getBoundingClientRect();
      mouse.x = ((ev.clientX - rect.left) / rect.width) * 2 - 1;
      mouse.y = -((ev.clientY - rect.top) / rect.height) * 2 + 1;
      ray.setFromCamera(mouse, stage.cam);
      var hits = ray.intersectObjects(bars, false);
      if (hits.length) {
        var a = hits[0].object.userData.area;
        hovered = hits[0].object; autoRotate = false;
        var nm = (a.name || "").replace(", New York", "");
        var html = '<div class="ht-name">' + escapeHtml(nm) + '</div>' +
          '<div class="ht-row"><span class="ht-score" style="color:var(--teal-300)">Index ' + a.index + '</span></div>' +
          (a.median_income != null ? '<div class="ht-meta">' + money(a.median_income) + ' median income</div>' : '') +
          (a.median_age != null ? '<div class="ht-meta">median age ' + a.median_age + '</div>' : '');
        positionTip(stage, ev.clientX, ev.clientY, html);
        stage.el.style.cursor = "pointer";
      } else {
        hovered = null; autoRotate = true; hideTip(stage); stage.el.style.cursor = "default";
      }
    }
    function onLeave() { hovered = null; autoRotate = true; hideTip(stage); stage.el.style.cursor = "default"; }
    stage.el.addEventListener("mousemove", onMove);
    stage.el.addEventListener("mouseleave", onLeave);

    var handle = runLoop(stage, function (dt, t) {
      if (autoRotate) root.rotation.y += dt * 0.18;
      for (var k = 0; k < bars.length; k++) {
        var b = bars[k];
        var lift = (b === hovered) ? 1.12 : 1;
        var breathe = 1 + 0.02 * Math.sin(t * 1.5 + k);
        var h = b.userData.baseH * lift * breathe;
        b.scale.y = h; b.position.y = h / 2;
        b.material.opacity = (b === hovered) ? 1 : 0.92;
      }
      grid.material.opacity = 0.3 + 0.08 * Math.sin(t * 1.2);
    }, function () {
      stage.el.removeEventListener("mousemove", onMove);
      stage.el.removeEventListener("mouseleave", onLeave);
    });

    REGISTRY[containerId] = handle;
    return handle;
  }

  /* ===========================================================================
   * 3) PIPELINE 3D — extruded bars for HOT / WARM / NURTURE premium.
   * Accepts { HOT, WARM, NURTURE } premium dollars.
   * ========================================================================= */
  function pipeline3D(containerId, pipelineByBucket) {
    disposeExisting(containerId);
    var stage = makeStage(containerId, { fov: 50, camX: 0, camY: 5.5, camZ: 12, lookAt: new THREE.Vector3(0, 1.5, 0) });
    if (!stage) return { dispose: function () {}, resize: function () {} };
    var data = pipelineByBucket || {};

    stage.scene.fog = new THREE.FogExp2(0x071a2e, 0.02);
    ambientParticles(stage.scene, 140, 26, COL.gold300, stage.disposables);

    var root = new THREE.Group();
    stage.scene.add(root);

    // base grid
    var grid = new THREE.GridHelper(14, 14, COL.navy700, COL.navy800);
    grid.material.transparent = true; grid.material.opacity = 0.3;
    root.add(grid);
    stage.disposables.push(grid.geometry, grid.material);

    var buckets = ["HOT", "WARM", "NURTURE"];
    var vals = buckets.map(function (b) { return +data[b] || 0; });
    var maxV = Math.max(1, Math.max.apply(null, vals));

    var bars = [], labels = [];
    var barGeo = new THREE.BoxGeometry(1.6, 1, 1.6);
    stage.disposables.push(barGeo);
    var glow = glowTexture();

    buckets.forEach(function (b, i) {
      var v = +data[b] || 0;
      var frac = v / maxV;
      var height = 0.4 + frac * 6.5;
      var x = (i - 1) * 3.0;
      var color = BUCKET_COLOR[b];

      var mat = new THREE.MeshBasicMaterial({ color: color, transparent: true, opacity: 0.9 });
      var bar = new THREE.Mesh(barGeo, mat);
      bar.scale.y = height; bar.position.set(x, height / 2, 0);
      stage.disposables.push(mat);

      var wmat = new THREE.MeshBasicMaterial({ color: color, wireframe: true, transparent: true, opacity: 0.35 });
      var wire = new THREE.Mesh(barGeo, wmat);
      wire.scale.set(1.06, height * 1.01, 1.06); wire.position.copy(bar.position);
      stage.disposables.push(wmat);

      // glow column at base
      var spMat = new THREE.SpriteMaterial({ map: glow, color: color, transparent: true, opacity: 0.5, depthWrite: false, blending: THREE.AdditiveBlending });
      var sp = new THREE.Sprite(spMat);
      sp.scale.setScalar(3.2); sp.position.set(x, 0.2, 0);
      stage.disposables.push(spMat);

      root.add(bar); root.add(wire); root.add(sp);
      bar.userData = { bucket: b, value: v, baseH: height };
      bars.push(bar);

      // floating text label sprite
      var lab = makeTextSprite(b + "  " + money(v), color);
      lab.position.set(x, height + 1.1, 0);
      lab.userData = { bar: bar };
      root.add(lab); labels.push(lab);
      stage.disposables.push(lab.material.map, lab.material);
    });

    /* hover raycaster (highlight) */
    var ray = new THREE.Raycaster();
    var mouse = new THREE.Vector2();
    var hovered = null;
    function onMove(ev) {
      var rect = stage.el.getBoundingClientRect();
      mouse.x = ((ev.clientX - rect.left) / rect.width) * 2 - 1;
      mouse.y = -((ev.clientY - rect.top) / rect.height) * 2 + 1;
      ray.setFromCamera(mouse, stage.cam);
      var hits = ray.intersectObjects(bars, false);
      if (hits.length) {
        hovered = hits[0].object;
        var u = hovered.userData;
        positionTip(stage, ev.clientX, ev.clientY,
          '<div class="ht-name">' + u.bucket + ' Pipeline</div>' +
          '<div class="ht-meta"><span class="ht-score">' + money(u.value) + '</span> est. annualized premium</div>');
        stage.el.style.cursor = "pointer";
      } else { hovered = null; hideTip(stage); stage.el.style.cursor = "default"; }
    }
    function onLeave() { hovered = null; hideTip(stage); stage.el.style.cursor = "default"; }
    stage.el.addEventListener("mousemove", onMove);
    stage.el.addEventListener("mouseleave", onLeave);

    var handle = runLoop(stage, function (dt, t) {
      root.rotation.y = Math.sin(t * 0.18) * 0.5; // gentle oscillating turntable
      for (var k = 0; k < bars.length; k++) {
        var b = bars[k];
        var hi = (b === hovered) ? 1.08 : 1;
        var breathe = 1 + 0.025 * Math.sin(t * 1.8 + k);
        var h = b.userData.baseH * hi * breathe;
        b.scale.y = h; b.position.y = h / 2;
        if (labels[k]) labels[k].position.y = h + 1.1;
        b.material.opacity = (b === hovered) ? 1 : 0.9;
      }
    }, function () {
      stage.el.removeEventListener("mousemove", onMove);
      stage.el.removeEventListener("mouseleave", onLeave);
    });

    REGISTRY[containerId] = handle;
    return handle;
  }

  /* ---------- text label sprite (canvas) ---------- */
  function makeTextSprite(text, color) {
    var pad = 24, fs = 44;
    var c = document.createElement("canvas");
    var ctx = c.getContext("2d");
    ctx.font = "600 " + fs + "px Inter, system-ui, sans-serif";
    var tw = ctx.measureText(text).width;
    c.width = Math.ceil(tw + pad * 2);
    c.height = fs + pad;
    ctx = c.getContext("2d");
    ctx.font = "600 " + fs + "px Inter, system-ui, sans-serif";
    ctx.textBaseline = "middle";
    // glow
    var hex = "#" + new THREE.Color(color).getHexString();
    ctx.shadowColor = hex; ctx.shadowBlur = 16;
    ctx.fillStyle = "#ffffff";
    ctx.fillText(text, pad, c.height / 2);
    var tex = new THREE.CanvasTexture(c);
    tex.minFilter = THREE.LinearFilter;
    var mat = new THREE.SpriteMaterial({ map: tex, transparent: true, depthWrite: false });
    var sp = new THREE.Sprite(mat);
    var scale = 0.012;
    sp.scale.set(c.width * scale, c.height * scale, 1);
    return sp;
  }

  function escapeHtml(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  /* ---------- public API ---------- */
  global.Holo = {
    leadConstellation: leadConstellation,
    territoryGlobe: territoryGlobe,
    pipeline3D: pipeline3D,
    dispose: function (containerId) { disposeExisting(containerId); },
    disposeAll: function () { Object.keys(REGISTRY).forEach(disposeExisting); },
    _registry: REGISTRY,
    version: "1.0.0"
  };
})(typeof window !== "undefined" ? window : this);
