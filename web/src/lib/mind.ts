/**
 * What the brain draws, as the API sends it.
 *
 * The shape is `GET /mind` (core/mind.py). Three kinds of node, and the rule
 * that decides everything about how they are drawn:
 *
 *   · `memory`  - a curated entry she has kept. The frame; it takes the stem
 *                 and the deep structures.
 *   · `session` - one conversation, spread over the cortex.
 *   · `message` - one thing said in it, sitting beside its session.
 *
 * `importance` is 0-10 **only where the entry records one** and `null`
 * everywhere else. Null is not zero and must not be rendered as zero: it means
 * she is holding the thing without a judgement attached, and the renderer draws
 * that hollow. Sessions and messages never carry one - importance is a property
 * of a memory, not of a conversation.
 *
 * `size` is always a real quantity, normalised to 0-1 by the server: a memory's
 * importance, a session's message count, a message's tokens. It is what the
 * radius is made of, so a circle's size always means something.
 */

export type MindKind = "memory" | "session" | "message";

export interface MindNode {
  id: string;
  kind: MindKind;
  title: string;
  /** The opening of the body, for the hover readout. */
  excerpt: string;
  at: string | null;
  /** 0-10 where it is recorded, null where it is not. Never defaulted. */
  importance: number | null;
  /** 0-1. Below 0.6 draws hollow - present, weight unknown. */
  confidence: number;
  /** 0-1, and always a real count. Drives the radius. */
  size: number;
  /** The real quantity, printed in the readout: "8/10", "12 msg", "assistant". */
  measure: string;
  source: string;
  /** Node **ids**, not titles - see core/mind.py for why the key changed. */
  relations: string[];
}

export interface MindSnapshot {
  available: boolean;
  detail: string;
  /** Whether Hermes will write memories at all. An empty store with memory
   *  switched off is a configuration fact, not an empty mind. */
  memory_enabled: boolean;
  counts: { memory: number; session: number; message: number };
  total: number;
  max_nodes: number;
  /** How many nodes are in context right now. Real: the live session and its
   *  messages, which is genuinely the context of her next turn. */
  budget: number;
  nodes: MindNode[];
  recalled: { id: string; hop: 0 | 1 | 2 }[];
  scan_ms: number;
}

export const EMPTY: MindSnapshot = {
  available: false,
  detail: "",
  memory_enabled: false,
  counts: { memory: 0, session: 0, message: 0 },
  total: 0,
  max_nodes: 72,
  budget: 0,
  nodes: [],
  recalled: [],
  scan_ms: 0,
};
