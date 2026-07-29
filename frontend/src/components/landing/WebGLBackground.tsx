"use client";

import { useEffect, useRef } from "react";

export default function WebGLBackground() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const gl = canvas.getContext("webgl") || canvas.getContext("experimental-webgl");
    if (!gl) return;

    const glCtx = gl as WebGLRenderingContext;

    const vsSource = `
      attribute vec2 a_position;
      varying vec2 v_texCoord;
      void main() {
        v_texCoord = a_position * 0.5 + 0.5;
        gl_Position = vec4(a_position, 0.0, 1.0);
      }
    `;

    const fsSource = `
      precision highp float;
      uniform float u_time;
      uniform vec2 u_resolution;
      uniform vec2 u_mouse;
      uniform float u_dark;
      varying vec2 v_texCoord;

      void main() {
        vec2 uv = v_texCoord;
        vec2 mouse = u_mouse / u_resolution;
        
        float dist = distance(uv, mouse);
        float wave = sin(uv.x * 8.0 + u_time * 0.4 + mouse.x * 4.0) * cos(uv.y * 8.0 - u_time * 0.2 + mouse.y * 4.0);
        
        vec3 color1 = mix(vec3(0.97, 0.98, 1.0), vec3(0.01, 0.02, 0.06), u_dark);
        vec3 color2 = mix(vec3(0.95, 0.96, 0.99), vec3(0.03, 0.04, 0.12), u_dark);
        vec3 accent = vec3(0.2, 0.15, 0.8);
        
        vec3 finalColor = mix(color1, color2, wave * 0.5 + 0.5);
        finalColor += accent * (1.0 - smoothstep(0.0, 0.8, dist)) * (0.02 + 0.15 * u_dark);
        
        gl_FragColor = vec4(finalColor, 1.0);
      }
    `;

    function createShader(gl: WebGLRenderingContext, type: number, source: string) {
      const shader = gl.createShader(type)!;
      gl.shaderSource(shader, source);
      gl.compileShader(shader);
      return shader;
    }

    const program = glCtx.createProgram()!;
    glCtx.attachShader(program, createShader(glCtx, glCtx.VERTEX_SHADER, vsSource));
    glCtx.attachShader(program, createShader(glCtx, glCtx.FRAGMENT_SHADER, fsSource));
    glCtx.linkProgram(program);

    const positionBuffer = glCtx.createBuffer();
    glCtx.bindBuffer(glCtx.ARRAY_BUFFER, positionBuffer);
    glCtx.bufferData(
      glCtx.ARRAY_BUFFER,
      new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]),
      glCtx.STATIC_DRAW
    );

    const positionLoc = glCtx.getAttribLocation(program, "a_position");
    const timeLoc = glCtx.getUniformLocation(program, "u_time");
    const resLoc = glCtx.getUniformLocation(program, "u_resolution");
    const mouseLoc = glCtx.getUniformLocation(program, "u_mouse");
    const darkLoc = glCtx.getUniformLocation(program, "u_dark");

    let mouseX = window.innerWidth / 2;
    let mouseY = window.innerHeight / 2;
    let animId: number;

    const onMouseMove = (e: MouseEvent) => {
      mouseX = e.clientX;
      mouseY = window.innerHeight - e.clientY;
    };
    window.addEventListener("mousemove", onMouseMove);

    function render(time: number) {
      canvas!.width = window.innerWidth;
      canvas!.height = window.innerHeight;
      glCtx.viewport(0, 0, canvas!.width, canvas!.height);

      glCtx.useProgram(program);
      glCtx.enableVertexAttribArray(positionLoc);
      glCtx.bindBuffer(glCtx.ARRAY_BUFFER, positionBuffer);
      glCtx.vertexAttribPointer(positionLoc, 2, glCtx.FLOAT, false, 0, 0);

      glCtx.uniform1f(timeLoc, time * 0.001);
      glCtx.uniform2f(resLoc, canvas!.width, canvas!.height);
      glCtx.uniform2f(mouseLoc, mouseX, mouseY);
      glCtx.uniform1f(
        darkLoc,
        document.documentElement.classList.contains("dark") ? 1.0 : 0.0
      );

      glCtx.drawArrays(glCtx.TRIANGLE_STRIP, 0, 4);
      animId = requestAnimationFrame(render);
    }
    animId = requestAnimationFrame(render);

    return () => {
      cancelAnimationFrame(animId);
      window.removeEventListener("mousemove", onMouseMove);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      className="fixed top-0 left-0 w-full h-full -z-1 pointer-events-none block"
    />
  );
}
