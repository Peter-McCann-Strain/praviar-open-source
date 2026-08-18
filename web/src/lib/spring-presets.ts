/**
 * Spring animation presets for consistent motion across the app.
 * Use these instead of duration-based transitions for natural, premium feel.
 *
 * Usage with motion/react:
 *   <motion.div transition={SPRING_SNAPPY} />
 *   <motion.div transition={springTransition("smooth")} />
 */

/** Snappy — buttons, toggles, small interactions */
export const SPRING_SNAPPY = {
  type: "spring" as const,
  stiffness: 300,
  damping: 30,
};

/** Smooth — panels, modals, medium-sized elements */
export const SPRING_SMOOTH = {
  type: "spring" as const,
  stiffness: 200,
  damping: 25,
};

/** Gentle — page transitions, large layout shifts */
export const SPRING_GENTLE = {
  type: "spring" as const,
  stiffness: 100,
  damping: 20,
};

const presets = {
  snappy: SPRING_SNAPPY,
  smooth: SPRING_SMOOTH,
  gentle: SPRING_GENTLE,
} as const;

type SpringPreset = keyof typeof presets;

/** Get a spring transition object by name */
export function springTransition(preset: SpringPreset) {
  return presets[preset];
}
