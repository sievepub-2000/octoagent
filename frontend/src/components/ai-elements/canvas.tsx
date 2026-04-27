import {
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  ReactFlow,
  type ReactFlowProps,
} from "@xyflow/react";
import type { ReactNode } from "react";
import "@xyflow/react/dist/style.css";

type CanvasProps = ReactFlowProps & {
  children?: ReactNode;
};

export const Canvas = ({ children, ...props }: CanvasProps) => (
  <ReactFlow
    deleteKeyCode={["Backspace", "Delete"]}
    fitView
    minZoom={0.35}
    panOnDrag
    panOnScroll
    selectionOnDrag={true}
    zoomOnDoubleClick={false}
    zoomOnPinch
    {...props}
  >
    <Background
      color="rgba(204, 145, 108, 0.22)"
      gap={22}
      size={1.25}
      variant={BackgroundVariant.Dots}
    />
    <MiniMap
      pannable
      zoomable
      bgColor="rgba(255,255,255,0.75)"
      className="rounded-2xl border border-border/40 shadow-[3px_3px_8px_var(--neu-dark),_-3px_-3px_8px_var(--neu-light)]"
      maskColor="rgba(244,233,222,0.22)"
      nodeBorderRadius={16}
      nodeColor="rgba(199, 119, 89, 0.72)"
      position="bottom-left"
    />
    <Controls className="rounded-2xl border border-border/40 bg-card/75 p-1 shadow-[3px_3px_8px_var(--neu-dark),_-3px_-3px_8px_var(--neu-light)] backdrop-blur" position="bottom-right" />
    {children}
  </ReactFlow>
);
