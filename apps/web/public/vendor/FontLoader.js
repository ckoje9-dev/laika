/* eslint-disable */
(function () {
  if (typeof THREE === "undefined") return;

  THREE.FontLoader = function (manager) {
    this.manager = manager !== undefined ? manager : THREE.DefaultLoadingManager;
    this.path = undefined;
    this.requestHeader = undefined;
    this.withCredentials = undefined;
  };

  Object.assign(THREE.FontLoader.prototype, {
    load: function (url, onLoad, onProgress, onError) {
      var loader = new THREE.FileLoader(this.manager);
      if (this.path !== undefined) loader.setPath(this.path);
      if (this.requestHeader !== undefined) loader.setRequestHeader(this.requestHeader);
      if (this.withCredentials !== undefined) loader.setWithCredentials(this.withCredentials);
      loader.load(
        url,
        function (text) {
          var json = JSON.parse(text);
          var font = this.parse(json);
          if (onLoad) onLoad(font);
        }.bind(this),
        onProgress,
        onError
      );
    },
    parse: function (json) {
      return new THREE.Font(json);
    },
    setPath: function (value) {
      this.path = value;
      return this;
    },
    setRequestHeader: function (value) {
      this.requestHeader = value;
      return this;
    },
    setWithCredentials: function (value) {
      this.withCredentials = value;
      return this;
    },
  });

  THREE.Font = function (data) {
    this.isFont = true;
    this.type = "Font";
    this.data = data;
  };

  Object.assign(THREE.Font.prototype, {
    generateShapes: function (text, size) {
      size = size === undefined ? 100 : size;
      var shapes = [];
      var paths = createPaths(text, size, this.data);
      for (var p = 0; p < paths.length; p++) {
        shapes = shapes.concat(paths[p].toShapes());
      }
      return shapes;
    },
  });

  function createPaths(text, size, data) {
    var chars = Array.from(text);
    var scale = size / data.resolution;
    var lineHeight =
      (data.boundingBox.yMax - data.boundingBox.yMin + data.underlineThickness) * scale;

    var paths = [];
    var offsetX = 0;
    var offsetY = 0;

    for (var i = 0; i < chars.length; i++) {
      var char = chars[i];
      if (char === "\n") {
        offsetX = 0;
        offsetY -= lineHeight;
        continue;
      }
      var path = createPath(char, scale, offsetX, offsetY, data);
      if (path) paths.push(path);
      var glyph = data.glyphs[char] || data.glyphs["?"];
      if (glyph) offsetX += glyph.ha * scale;
    }

    return paths;
  }

  function createPath(char, scale, offsetX, offsetY, data) {
    var glyph = data.glyphs[char] || data.glyphs["?"];
    if (!glyph) return null;

    var path = new THREE.ShapePath();
    var outline = glyph.o;
    if (!outline) return path;

    var outlinePoints = outline.split(" ");
    var x = 0;
    var y = 0;
    for (var i = 0; i < outlinePoints.length; ) {
      var action = outlinePoints[i++];
      if (action === "m") {
        x = outlinePoints[i++] * scale + offsetX;
        y = outlinePoints[i++] * scale + offsetY;
        path.moveTo(x, y);
      } else if (action === "l") {
        x = outlinePoints[i++] * scale + offsetX;
        y = outlinePoints[i++] * scale + offsetY;
        path.lineTo(x, y);
      } else if (action === "q") {
        var cpx = outlinePoints[i++] * scale + offsetX;
        var cpy = outlinePoints[i++] * scale + offsetY;
        var cpx1 = outlinePoints[i++] * scale + offsetX;
        var cpy1 = outlinePoints[i++] * scale + offsetY;
        path.quadraticCurveTo(cpx, cpy, cpx1, cpy1);
        x = cpx1;
        y = cpy1;
      } else if (action === "b") {
        var cpx2 = outlinePoints[i++] * scale + offsetX;
        var cpy2 = outlinePoints[i++] * scale + offsetY;
        var cpx3 = outlinePoints[i++] * scale + offsetX;
        var cpy3 = outlinePoints[i++] * scale + offsetY;
        var cpx4 = outlinePoints[i++] * scale + offsetX;
        var cpy4 = outlinePoints[i++] * scale + offsetY;
        path.bezierCurveTo(cpx2, cpy2, cpx3, cpy3, cpx4, cpy4);
        x = cpx4;
        y = cpy4;
      }
    }
    return path;
  }
})();
