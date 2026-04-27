"use client";

import { useDeferredValue, useMemo } from "react";
import type { HTMLAttributes } from "react";

import {
  MessageResponse,
  type MessageResponseProps,
} from "@/components/ai-elements/message";
import { streamdownPlugins } from "@/core/streamdown";

import { CitationLink } from "../citations/citation-link";

export type MarkdownContentProps = {
  content: string;
  isLoading: boolean;
  rehypePlugins: MessageResponseProps["rehypePlugins"];
  className?: string;
  remarkPlugins?: MessageResponseProps["remarkPlugins"];
  components?: MessageResponseProps["components"];
};

/** Renders markdown content. */
/** Renders markdown content.
 *
 * During active streaming, historical (non-streaming) messages defer their
 * markdown re-parse via `useDeferredValue` so the live streaming message
 * stays responsive.
 */
export function MarkdownContent({
  content,
  isLoading,
  rehypePlugins,
  className,
  remarkPlugins = streamdownPlugins.remarkPlugins,
  components: componentsFromProps,
}: MarkdownContentProps) {
    // Defer re-parse of historical content while streaming is active.
    const deferredContent = useDeferredValue(content);
    const displayContent = isLoading ? content : deferredContent;

  const components = useMemo(() => {
    return {
      a: (props: HTMLAttributes<HTMLAnchorElement>) => {
        if (typeof props.children === "string") {
          const match = /^citation:(.+)$/.exec(props.children);
          if (match) {
            const [, text] = match;
            return <CitationLink {...props}>{text}</CitationLink>;
          }
        }
        return <a {...props} />;
      },
      ...componentsFromProps,
    };
  }, [componentsFromProps]);

  if (!content) return null;
  if (!displayContent) return null;

  return (
    <MessageResponse
      className={className}
      remarkPlugins={remarkPlugins}
      rehypePlugins={rehypePlugins}
      components={components}
    >
      {displayContent}
    </MessageResponse>
  );
}
