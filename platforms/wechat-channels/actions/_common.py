"""Pure helpers shared by WeChat Channels browser actions."""
from __future__ import annotations

import json
import re
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

MANAGER_URL = "https://channels.weixin.qq.com/platform/post/list"

STATUS_LABELS: tuple[tuple[str, str], ...] = (
    ("审核中", "reviewing"),
    ("未通过", "rejected"),
    ("草稿", "draft"),
    ("已发布", "published"),
    ("已发表", "published"),
)

_ID_PRIORITY: tuple[str, ...] = (
    "finderobjectid",
    "postid",
    "contentid",
    "videoid",
    "objectid",
    "exportid",
    "feedid",
    "mediaid",
)


def status_label(text: str) -> tuple[Optional[str], Optional[str]]:
    for label, status in STATUS_LABELS:
        if label in text:
            return status, label
    return None, None


def _normalized_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]", "", key.lower())


def _ids_from_query(value: str) -> dict[str, str]:
    parsed = urlparse(value)
    if not parsed.query:
        return {}
    result: dict[str, str] = {}
    for key, values in parse_qs(parsed.query).items():
        normalized = _normalized_key(key)
        if normalized in _ID_PRIORITY and values:
            result[normalized] = values[0]
    return result


def extract_stable_id(row: dict[str, Any]) -> Optional[str]:
    ids = dict(row.get("stable_ids") or {})
    for source in row.get("urls") or []:
        ids.update(_ids_from_query(str(source)))
    for key in _ID_PRIORITY:
        if ids.get(key):
            return ids[key]
    return None


def choose_manager_row(
    rows: list[dict[str, Any]],
    post_id: Optional[str],
    title: Optional[str],
    desc: Optional[str],
) -> Optional[dict[str, Any]]:
    if post_id:
        matches = [row for row in rows if extract_stable_id(row) == post_id]
    elif title:
        matches = [row for row in rows if title in row.get("text", "")]
    elif desc:
        matches = [row for row in rows if desc in row.get("text", "")]
    else:
        return None
    if not matches:
        return None
    return min(matches, key=lambda row: len(row.get("text", "")))


def manager_scan_expression(
    post_id: Optional[str],
    title: Optional[str],
    desc: Optional[str],
) -> str:
    values = (
        json.dumps(post_id or ""),
        json.dumps(title or ""),
        json.dumps(desc or ""),
    )
    return """
(() => {
  const root = document.querySelector('wujie-app')?.shadowRoot;
  const body = root?.querySelector('body') || root;
  if (!body) return '[]';
  const priority = ['finderobjectid', 'postid', 'contentid', 'videoid', 'objectid', 'exportid', 'feedid', 'mediaid'];
  const labels = ['审核中', '未通过', '草稿', '已发布', '已发表'];
  const normalize = (value) => value.toLowerCase().replace(/[^a-z0-9]/g, '');
  const targetPostId = %s;
  const targetTitle = %s;
  const targetDesc = %s;
  const candidates = new Map();
  const addCandidate = (element, kind, stableIds) => {
    const attributes = {};
    for (const attribute of element.attributes || []) {
      const name = attribute.name.toLowerCase();
      if (name.startsWith('data-') || ['aria-label', 'title'].includes(name)) attributes[name] = attribute.value;
    }
    const urls = [];
    for (const anchor of element.querySelectorAll('a[href]')) {
      if (anchor.href) urls.push(anchor.href);
    }
    const text = (element.innerText || element.textContent || '').replace(/\\s+/g, ' ').trim();
    if (!text || text.length > 3000) return;
    const encodedIds = Array.from(stableIds.entries()).sort().map(([key, value]) => `${key}=${value}`).join(';');
    const key = `${kind}:${encodedIds}:${text}`;
    if (candidates.has(key)) return;
    candidates.set(key, {kind, stable_ids: Object.fromEntries(stableIds), attributes, urls, text, tag: element.tagName.toLowerCase()});
  };
  const collectIds = (element) => {
    const ids = new Map();
    for (const attribute of element.attributes || []) {
      const normalized = normalize(attribute.name);
      const value = attribute.value.trim();
      if (value && priority.includes(normalized)) ids.set(normalized, value);
    }
    return ids;
  };
  for (const element of body.querySelectorAll('*')) {
    const ids = collectIds(element);
    const text = element.innerText || element.textContent || '';
    if ((targetTitle && text.includes(targetTitle)) || (targetDesc && text.includes(targetDesc))) {
      let textCandidate = element;
      let textIds = ids;
      for (let depth = 0; textCandidate && textCandidate !== body && depth < 12; depth += 1) {
        const candidateText = textCandidate.innerText || textCandidate.textContent || '';
        const candidateIds = collectIds(textCandidate);
        if (labels.some((label) => candidateText.includes(label)) || candidateIds.size) {
          textIds = candidateIds;
          break;
        }
        textCandidate = textCandidate.parentElement;
      }
      addCandidate(textCandidate && textCandidate !== body ? textCandidate : element, 'text', textIds);
    }
    if (!ids.size) continue;
    let labeled = null;
    let cursor = element;
    for (let depth = 0; cursor && cursor !== body && depth < 12; depth += 1) {
      const cursorText = cursor.innerText || cursor.textContent || '';
      if (labels.some((label) => cursorText.includes(label))) {
        labeled = cursor;
        break;
      }
      cursor = cursor.parentElement;
    }
    addCandidate(labeled || element, 'id', ids);
  }
  return JSON.stringify(Array.from(candidates.values()));
})()
""".strip() % values
