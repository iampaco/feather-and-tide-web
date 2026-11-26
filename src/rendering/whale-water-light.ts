// The same projected light falls across submerged shapes at their own height.
export const whaleWaterLight = `
  float whaleRefractedLight(vec3 point, float time) {
    vec2 p = point.xz + point.y * vec2(0.29, -0.21);
    float fold = sin(dot(p, vec2(0.16, 0.13)) + time * 0.42);
    float sweep = sin(dot(p, vec2(-0.12, 0.19)) - time * 0.37);
    float first = sin(dot(p, vec2(0.65, 0.38)) + fold + time * 0.57);
    float second = sin(dot(p, vec2(-0.38, 0.61)) + sweep - time * 0.52);
    float edge = 1.0 - smoothstep(0.08, 0.33, abs(first + second * 0.72));
    return edge * (0.32 + 0.68 * smoothstep(0.12, 0.88, abs(second)));
  }

  // Sight-line distance mainly affects the far reef, while the actual height
  // below the surface separates whales that dive at different times.
  vec3 whaleThroughWater(vec3 pigment, float worldHeight, float eyeDepth, float dive, float strength) {
    float below = max(0.0, -worldHeight);
    float submerged = smoothstep(0.0, 0.9, below);
    float descent = smoothstep(0.08, 1.95, dive);
    float distancePastPod = max(eyeDepth - 81.0, 0.0);
    float opticalDepth = below * mix(0.027, 0.072, descent)
                       + distancePastPod * mix(0.004, 0.022, descent);
    float transmission = exp(-opticalDepth);
    vec3 water = mix(vec3(0.079, 0.278, 0.309), vec3(0.019, 0.079, 0.148), descent);
    vec3 filtered = pigment * vec3(
      mix(transmission, transmission * transmission, 0.62),
      transmission,
      mix(transmission, 1.0, 0.13)
    );
    return mix(pigment, filtered + water * (1.0 - transmission), submerged * strength);
  }
`;
