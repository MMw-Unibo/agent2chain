const LEVEL_LABELS = {
  1: "Beginner",
  2: "Intermediate",
  3: "Expert",
};

export function normalizeKnowledgeLevel(level) {
  const raw = String(level ?? "").trim().toLowerCase();
  if (["1", "beginner", "level 1", "novice"].includes(raw)) {
    return LEVEL_LABELS[1];
  }
  if (["2", "intermediate", "level 2"].includes(raw)) {
    return LEVEL_LABELS[2];
  }
  if (["3", "expert", "level 3", "advanced"].includes(raw)) {
    return LEVEL_LABELS[3];
  }
  return LEVEL_LABELS[1];
}

export function setKnowledgeLevel(node, level) {
  if (!node) {
    return;
  }
  node.textContent = normalizeKnowledgeLevel(level);
}

export function extractKnowledgeLevelMarker(rawReply) {
  const lines = String(rawReply || "").split("\n");
  const visibleLines = [];
  let level = null;

  for (const line of lines) {
    if (!line.startsWith("__KNOWLEDGE_LEVEL__")) {
      visibleLines.push(line);
      continue;
    }

    const rawLevel = line.slice("__KNOWLEDGE_LEVEL__".length).trim();
    const parsedLevel = Number.parseInt(rawLevel, 10);
    if ([1, 2, 3].includes(parsedLevel)) {
      level = parsedLevel;
    }
  }

  return {
    replyText: visibleLines.join("\n").trim(),
    level,
  };
}

export async function syncKnowledgeLevelFromServer(setKnowledgeLevelFn) {
  try {
    const response = await fetch("/api/knowledge-level");
    if (!response.ok) {
      setKnowledgeLevelFn(1);
      return;
    }

    const payload = await response.json();
    if ([1, 2, 3].includes(payload?.level)) {
      setKnowledgeLevelFn(payload.level);
      return;
    }

    setKnowledgeLevelFn(1);
  } catch {
    setKnowledgeLevelFn(1);
  }
}
