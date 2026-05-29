import { useEffect, useMemo, useRef, useState } from "react";

export type StreamRendererOptions = {
  fps?: number;
  chunkSize?: number;
  autoscroll?: boolean;
};

export function useStreamRenderer(
  sourceText: string,
  { fps = 30, chunkSize = 6, autoscroll = true }: StreamRendererOptions = {},
) {
  const [displayText, setDisplayText] = useState(sourceText);
  const sourceRef = useRef(sourceText);
  const renderedRef = useRef(sourceText);
  const frameRef = useRef<number | null>(null);
  const lastFrameAtRef = useRef(0);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const scrollAnchorRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    sourceRef.current = sourceText;
    if (!sourceText.startsWith(renderedRef.current)) {
      renderedRef.current = sourceText;
      setDisplayText(sourceText);
      return;
    }

    const frameInterval = 1000 / Math.max(1, fps);

    const renderFrame = (timestamp: number) => {
      if (timestamp - lastFrameAtRef.current < frameInterval) {
        frameRef.current = requestAnimationFrame(renderFrame);
        return;
      }
      lastFrameAtRef.current = timestamp;

      const target = sourceRef.current;
      const current = renderedRef.current;
      if (current.length >= target.length) {
        frameRef.current = null;
        return;
      }

      const next = target.slice(
        0,
        Math.min(target.length, current.length + Math.max(1, chunkSize)),
      );
      renderedRef.current = next;
      setDisplayText(next);
      if (autoscroll) {
        requestAnimationFrame(() => {
          scrollAnchorRef.current?.scrollIntoView({ block: "end" });
        });
      }
      frameRef.current = requestAnimationFrame(renderFrame);
    };

    frameRef.current ??= requestAnimationFrame(renderFrame);

    return () => {
      if (frameRef.current != null) {
        cancelAnimationFrame(frameRef.current);
        frameRef.current = null;
      }
    };
  }, [autoscroll, chunkSize, fps, sourceText]);

  const messageBubbleStyle = useMemo(
    () =>
      ({
        contain: "content",
        overflowAnchor: "none",
        willChange: "contents",
      }) as React.CSSProperties,
    [],
  );

  return {
    containerRef,
    displayText,
    messageBubbleStyle,
    scrollAnchorRef,
  };
}
