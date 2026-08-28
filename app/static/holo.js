/*
 * RETIRED / INERT COMPATIBILITY STUB.
 *
 * The current Evidence-Backed Broker Research surface does not load a 3D data
 * module. This anonymously served path remains only to fail closed for stale
 * bookmarks and cached clients. It renders nothing and accepts no data.
 */
(function retireHolo(global) {
  "use strict";

  global.Holo = Object.freeze({
    retired: true,
    dispose: function dispose() {},
    disposeAll: function disposeAll() {},
  });
})(window);
