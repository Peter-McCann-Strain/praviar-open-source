import * as React from "react";

type MotionMockOptions = {
  useInView?: () => boolean;
  useReducedMotion?: () => boolean;
};

const MOTION_PROP_NAMES = new Set([
  "animate",
  "custom",
  "drag",
  "exit",
  "initial",
  "layout",
  "layoutId",
  "transition",
  "variants",
  "viewport",
  "whileDrag",
  "whileFocus",
  "whileHover",
  "whileInView",
  "whileTap",
]);

function stripMotionProps(props: Record<string, unknown>) {
  return Object.fromEntries(
    Object.entries(props).filter(([key]) => !MOTION_PROP_NAMES.has(key)),
  );
}

function createMotionElement(tag: keyof JSX.IntrinsicElements) {
  return React.forwardRef<HTMLElement, Record<string, unknown>>(
    ({ children, ...props }, ref) =>
      React.createElement(tag, { ref, ...stripMotionProps(props) }, children),
  );
}

export function createMotionMock(options: MotionMockOptions = {}) {
  const motionCache = new Map<string, React.ComponentType<any>>();
  const motion = new Proxy(
    {},
    {
      get: (_target, prop: string | symbol) => {
        if (typeof prop !== "string") return undefined;
        if (!motionCache.has(prop)) {
          motionCache.set(
            prop,
            createMotionElement(prop as keyof JSX.IntrinsicElements),
          );
        }
        return motionCache.get(prop);
      },
    },
  );

  return {
    motion,
    AnimatePresence: ({ children }: { children: React.ReactNode }) => (
      <>{children}</>
    ),
    useInView: options.useInView ?? (() => false),
    useReducedMotion: options.useReducedMotion ?? (() => false),
  };
}
