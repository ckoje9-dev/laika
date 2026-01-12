/* eslint-disable */
(function () {
  if (typeof THREE === "undefined" || THREE.TextGeometry) return;

  class TextGeometry extends THREE.ExtrudeGeometry {
    constructor(text, parameters = {}) {
      const font = parameters.font;
      if (!font || !font.generateShapes) {
        throw new Error("TextGeometry requires a font with generateShapes()");
      }
      const size = parameters.size !== undefined ? parameters.size : 100;
      const height = parameters.height !== undefined ? parameters.height : 50;
      const curveSegments =
        parameters.curveSegments !== undefined ? parameters.curveSegments : 12;
      const bevelEnabled = parameters.bevelEnabled === true;
      const bevelThickness =
        parameters.bevelThickness !== undefined ? parameters.bevelThickness : 10;
      const bevelSize =
        parameters.bevelSize !== undefined ? parameters.bevelSize : 8;
      const bevelOffset =
        parameters.bevelOffset !== undefined ? parameters.bevelOffset : 0;
      const bevelSegments =
        parameters.bevelSegments !== undefined ? parameters.bevelSegments : 3;

      const shapes = font.generateShapes(text, size);
      super(shapes, {
        depth: height,
        bevelEnabled,
        bevelThickness,
        bevelSize,
        bevelOffset,
        bevelSegments,
        curveSegments,
      });

      this.type = "TextGeometry";
      this.parameters = {
        text,
        font,
        size,
        height,
        curveSegments,
        bevelEnabled,
        bevelThickness,
        bevelSize,
        bevelOffset,
        bevelSegments,
      };
    }
  }

  THREE.TextGeometry = TextGeometry;
})();
