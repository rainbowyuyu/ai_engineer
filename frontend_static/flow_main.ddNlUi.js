/**
 * 设计域专步 AI：稳定 JSON 序列化 + 行级 diff（用于「建议参数」相对上一版的可视化）
 */

export function stableSortKeysDeep(v) {
  if (v === null || typeof v !== "object") return v;
  if (Array.isArray(v)) return v.map((x) => stableSortKeysDeep(x));
  const o = {};
  for (const k of Object.keys(v).sort()) {
    o[k] = stableSortKeysDeep(v[k]);
  }
  return o;
}

/**
 * @param {string} aStr
 * @param {string} bStr
 * @returns {{ op: "same"|"add"|"del"; text: string }[]}
 */
export function diffLineStrings(aStr, bStr) {
  const A = aStr ? String(aStr).split("\n") : [];
  const B = bStr ? String(bStr).split("\n") : [];
  const n = A.length;
  const m = B.length;
  const dp = Array.from({ length: n + 1 }, () => new Array(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i -= 1) {
    for (let j = m - 1; j >= 0; j -= 1) {
      dp[i][j] = A[i] === B[j] ? 1 + dp[i + 1][j + 1] : Math.max(dp[i + 1][j], dp[i][j + 1]);
    }
  }
  /** @type {{ op: "same"|"add"|"del"; text: string }[]} */
  const out = [];
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (A[i] === B[j]) {
      out.push({ op: "same", text: A[i] });
      i += 1;
      j += 1;
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      out.push({ op: "del", text: A[i] });
      i += 1;
    } else {
      out.push({ op: "add", text: B[j] });
      j += 1;
    }
  }
  while (i < n) {
    out.push({ op: "del", text: A[i] });
    i += 1;
  }
  while (j < m) {
    out.push({ op: "add", text: B[j] });
    j += 1;
  }
  return out;
}

export function diffHasStructuralChange(rows) {
  return rows.some((r) => r.op === "add" || r.op === "del");
}

export function diffSummaryCounts(rows) {
  let add = 0;
  let del = 0;
  for (const r of rows) {
    if (r.op === "add") add += 1;
    if (r.op === "del") del += 1;
  }
  return { add, del };
}
