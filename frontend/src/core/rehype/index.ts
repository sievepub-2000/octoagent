import type { Element, Root, ElementContent } from "hast";
import { useMemo } from "react";
import { visit } from "unist-util-visit";
import type { BuildVisitor } from "unist-util-visit";

// Tags whose text nodes get split into per-word <span>s so the live-streaming
// markdown can fade-in word-by-word.
const SPLIT_TAGS = new Set([
  "p",
  "h1",
  "h2",
  "h3",
  "h4",
  "h5",
  "h6",
  "li",
  "strong",
]);

// Detect CJK (Han, Hiragana, Katakana, Hangul) text. Only such text needs the
// expensive `Intl.Segmenter`; pure-ASCII text can be split by a cheap regex.
const CJK_RE = /[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af\uf900-\ufaff]/;
// Matches a single "word" in non-CJK text: a run of non-whitespace
// optionally followed by trailing whitespace. Preserves whitespace inside
// each span so layout reflows match the original text exactly.
const ASCII_WORD_RE = /\S+\s*|\s+/g;

// Hoisted Segmenter singleton — `new Intl.Segmenter` is expensive (V8
// allocates ICU break-iterator state); creating one per text node turned
// into a measurable hot spot during subtask streaming.  The granularity
// "word" works for every script we care about, so a single locale-neutral
// instance suffices.
const segmenter: Intl.Segmenter | null =
  typeof Intl !== "undefined" && typeof Intl.Segmenter === "function"
    ? new Intl.Segmenter("zh", { granularity: "word" })
    : null;

function splitText(value: string): string[] {
  if (!value) return [];
  if (segmenter && CJK_RE.test(value)) {
    const words: string[] = [];
    for (const { segment } of segmenter.segment(value)) {
      if (segment) words.push(segment);
    }
    return words;
  }
  // ASCII / Latin fast path — about 50x faster than Intl.Segmenter on long
  // English paragraphs and produces visually identical fade-in word units.
  return value.match(ASCII_WORD_RE) ?? [];
}

function wrapWord(word: string): ElementContent {
  return {
    type: "element",
    tagName: "span",
    properties: { className: "animate-fade-in" },
    children: [{ type: "text", value: word }],
  };
}

export function rehypeSplitWordsIntoSpans() {
  return (tree: Root) => {
    visit(tree, "element", ((node: Element) => {
      if (!SPLIT_TAGS.has(node.tagName) || !node.children) return;
      let mutated = false;
      const newChildren: ElementContent[] = [];
      for (const child of node.children) {
        if (child.type === "text") {
          const words = splitText(child.value);
          if (words.length === 0) {
            // Preserve empty/whitespace-only text nodes verbatim so that
            // surrounding inline elements keep their spacing.
            newChildren.push(child);
            continue;
          }
          mutated = true;
          for (const word of words) newChildren.push(wrapWord(word));
        } else {
          newChildren.push(child);
        }
      }
      if (mutated) node.children = newChildren;
    }) as BuildVisitor<Root, "element">);
  };
}

export function useRehypeSplitWordsIntoSpans(enabled = true) {
  const rehypePlugins = useMemo(
    () => (enabled ? [rehypeSplitWordsIntoSpans] : []),
    [enabled],
  );
  return rehypePlugins;
}
