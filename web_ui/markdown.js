function markdownEscapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function sanitizeMarkdownUrl(url) {
  const value = String(url || "").trim();
  if (/^(https?:|mailto:)/i.test(value)) return value;
  if (value.startsWith("#") || value.startsWith("/")) return value;
  return "";
}

function unescapeMarkdownPunctuation(html) {
  return String(html ?? "").replace(/\\([\\`*_{}\[\]()#+\-.!%])/g, "$1");
}

function renderMathText(text) {
  return unescapeMarkdownPunctuation(markdownEscapeHtml(text));
}

function mathToken(parts, html) {
  const token = `\u0000MATH${parts.length}\u0000`;
  parts.push(html);
  return token;
}

function readBracedContent(source, openIndex) {
  if (source[openIndex] !== "{") return null;
  let depth = 0;
  let content = "";
  for (let index = openIndex; index < source.length; index += 1) {
    const char = source[index];
    const previous = source[index - 1];
    if (char === "{" && previous !== "\\") {
      if (depth > 0) content += char;
      depth += 1;
      continue;
    }
    if (char === "}" && previous !== "\\") {
      depth -= 1;
      if (depth === 0) {
        return { content, endIndex: index };
      }
      content += char;
      continue;
    }
    if (depth > 0) content += char;
  }
  return null;
}

function skipMathWhitespace(source, index) {
  let cursor = index;
  while (cursor < source.length && /\s/.test(source[cursor])) {
    cursor += 1;
  }
  return cursor;
}

function replaceOneArgMathCommand(source, command, replacer) {
  const marker = `\\${command}`;
  let result = "";
  let cursor = 0;

  while (cursor < source.length) {
    const start = source.indexOf(marker, cursor);
    if (start < 0) {
      result += source.slice(cursor);
      break;
    }

    result += source.slice(cursor, start);
    let braceIndex = skipMathWhitespace(source, start + marker.length);
    if (source[braceIndex] !== "{") {
      result += marker;
      cursor = start + marker.length;
      continue;
    }

    const parsed = readBracedContent(source, braceIndex);
    if (!parsed) {
      result += source.slice(start);
      break;
    }

    result += replacer(parsed.content);
    cursor = parsed.endIndex + 1;
  }

  return result;
}

function replaceFracMathCommand(source, parts) {
  const marker = "\\frac";
  let result = "";
  let cursor = 0;

  while (cursor < source.length) {
    const start = source.indexOf(marker, cursor);
    if (start < 0) {
      result += source.slice(cursor);
      break;
    }

    result += source.slice(cursor, start);
    let numeratorIndex = skipMathWhitespace(source, start + marker.length);
    const numerator = readBracedContent(source, numeratorIndex);
    if (!numerator) {
      result += marker;
      cursor = start + marker.length;
      continue;
    }

    let denominatorIndex = skipMathWhitespace(source, numerator.endIndex + 1);
    const denominator = readBracedContent(source, denominatorIndex);
    if (!denominator) {
      result += source.slice(start, numerator.endIndex + 1);
      cursor = numerator.endIndex + 1;
      continue;
    }

    result += mathToken(
      parts,
      `<span class="math-frac"><span class="math-num">${renderMathExpression(numerator.content)}</span><span class="math-den">${renderMathExpression(denominator.content)}</span></span>`,
    );
    cursor = denominator.endIndex + 1;
  }

  return result;
}

function normalizeMathSource(expression) {
  return String(expression ?? "")
    .replace(/\r\n/g, "\n")
    .replace(/\\begin\{(?:equation\*?|align\*?|aligned|gather\*?|matrix)\}/g, "")
    .replace(/\\end\{(?:equation\*?|align\*?|aligned|gather\*?|matrix)\}/g, "")
    .replace(/\\\\/g, " ")
    .replace(/&/g, "")
    .replace(/\\left\s*/g, "")
    .replace(/\\right\s*/g, "")
    .replace(/\n+/g, " ")
    .trim();
}

function renderMathExpression(expression) {
  let source = normalizeMathSource(expression);
  const parts = [];

  source = replaceFracMathCommand(source, parts);

  for (const command of ["operatorname", "textrm", "mathrm", "text"]) {
    source = replaceOneArgMathCommand(source, command, (text) =>
      mathToken(parts, `<span class="math-text">${renderMathText(text)}</span>`),
    );
  }

  source = replaceOneArgMathCommand(source, "mathbf", (text) =>
    mathToken(parts, `<strong>${renderMathExpression(text)}</strong>`),
  );
  source = replaceOneArgMathCommand(source, "mathit", (text) =>
    mathToken(parts, `<em>${renderMathExpression(text)}</em>`),
  );
  source = replaceOneArgMathCommand(source, "sqrt", (text) =>
    mathToken(parts, `<span class="math-sqrt"><span class="math-root">√</span><span class="math-radicand">${renderMathExpression(text)}</span></span>`),
  );

  let html = markdownEscapeHtml(source)
    .replaceAll("\\times", "×")
    .replaceAll("\\cdot", "·")
    .replaceAll("\\div", "÷")
    .replaceAll("\\pm", "±")
    .replaceAll("\\mp", "∓")
    .replaceAll("\\leq", "≤")
    .replaceAll("\\le", "≤")
    .replaceAll("\\geq", "≥")
    .replaceAll("\\ge", "≥")
    .replaceAll("\\neq", "≠")
    .replaceAll("\\ne", "≠")
    .replaceAll("\\approx", "≈")
    .replaceAll("\\sim", "∼")
    .replaceAll("\\infty", "∞")
    .replaceAll("\\partial", "∂")
    .replaceAll("\\nabla", "∇")
    .replaceAll("\\sum", "∑")
    .replaceAll("\\prod", "∏")
    .replaceAll("\\int", "∫")
    .replaceAll("\\rightarrow", "→")
    .replaceAll("\\leftarrow", "←")
    .replaceAll("\\leftrightarrow", "↔")
    .replaceAll("\\to", "→")
    .replaceAll("\\alpha", "α")
    .replaceAll("\\beta", "β")
    .replaceAll("\\gamma", "γ")
    .replaceAll("\\delta", "δ")
    .replaceAll("\\epsilon", "ε")
    .replaceAll("\\theta", "θ")
    .replaceAll("\\lambda", "λ")
    .replaceAll("\\Delta", "Δ")
    .replaceAll("\\mu", "μ")
    .replaceAll("\\sigma", "σ")
    .replaceAll("\\Sigma", "Σ")
    .replaceAll("\\omega", "ω")
    .replaceAll("\\Omega", "Ω")
    .replaceAll("\\pi", "π")
    .replaceAll("\\%", "%")
    .replaceAll("\\_", "_")
    .replaceAll("\\,", " ")
    .replaceAll("\\;", " ")
    .replaceAll("\\:", " ")
    .replaceAll("\\!", "")
    .replaceAll("\\quad", " ")
    .replaceAll("\\qquad", " ");

  html = html.replace(/\\(sin|cos|tan|log|ln|exp|min|max|lim)\b/g, "$1");

  html = html.replace(/\^\{([^{}]+)\}/g, "<sup>$1</sup>");
  html = html.replace(/_\{([^{}]+)\}/g, "<sub>$1</sub>");
  html = html.replace(/\^([A-Za-z0-9+\-=]+)/g, "<sup>$1</sup>");
  html = html.replace(/_([A-Za-z0-9+\-=]+)/g, "<sub>$1</sub>");
  html = html.replace(/\s+/g, " ").trim();

  for (const [index, part] of parts.entries()) {
    html = html.replaceAll(`\u0000MATH${index}\u0000`, part);
  }
  return html;
}

function renderMathInline(expression) {
  return `<span class="math-inline">${renderMathExpression(expression)}</span>`;
}

function renderMathBlock(expression) {
  return `<div class="math-block"><span class="math-expression">${renderMathExpression(expression)}</span></div>`;
}

function collectDelimitedMath(lines, startIndex, opening, closing) {
  const first = lines[startIndex].trim();
  let content = first.slice(opening.length).trim();
  const parts = [];
  let closeIndex = content.indexOf(closing);
  if (closeIndex >= 0) {
    return {
      content: content.slice(0, closeIndex).trim(),
      endIndex: startIndex,
    };
  }

  if (content) parts.push(content);
  for (let index = startIndex + 1; index < lines.length; index += 1) {
    const line = lines[index].trim();
    closeIndex = line.indexOf(closing);
    if (closeIndex >= 0) {
      const beforeClose = line.slice(0, closeIndex).trim();
      if (beforeClose) parts.push(beforeClose);
      return {
        content: parts.join("\n").trim(),
        endIndex: index,
      };
    }
    parts.push(line);
  }
  return null;
}

function collectMathEnvironment(lines, startIndex) {
  const supported = "equation\\*?|align\\*?|aligned|gather\\*?|matrix";
  const first = lines[startIndex].trim();
  const openMatch = first.match(new RegExp(`^\\\\begin\\{(${supported})\\}`));
  if (!openMatch) return null;

  const environment = openMatch[1];
  const closing = `\\end{${environment}}`;
  let content = first.slice(openMatch[0].length).trim();
  const parts = [];
  let closeIndex = content.indexOf(closing);
  if (closeIndex >= 0) {
    return {
      content: content.slice(0, closeIndex).trim(),
      endIndex: startIndex,
    };
  }

  if (content) parts.push(content);
  for (let index = startIndex + 1; index < lines.length; index += 1) {
    const line = lines[index].trim();
    closeIndex = line.indexOf(closing);
    if (closeIndex >= 0) {
      const beforeClose = line.slice(0, closeIndex).trim();
      if (beforeClose) parts.push(beforeClose);
      return {
        content: parts.join("\n").trim(),
        endIndex: index,
      };
    }
    parts.push(line);
  }
  return null;
}

function renderInlineMarkdown(text) {
  const inlineParts = [];
  let source = String(text ?? "");

  source = source.replace(/`([^`]+)`/g, (_, code) => {
    const token = `\u0000INLINE${inlineParts.length}\u0000`;
    inlineParts.push(`<code>${markdownEscapeHtml(code)}</code>`);
    return token;
  });

  source = source.replace(/\\\[(.+?)\\\]/g, (_, math) => {
    const token = `\u0000INLINE${inlineParts.length}\u0000`;
    inlineParts.push(renderMathInline(math));
    return token;
  });

  source = source.replace(/\\\((.+?)\\\)/g, (_, math) => {
    const token = `\u0000INLINE${inlineParts.length}\u0000`;
    inlineParts.push(renderMathInline(math));
    return token;
  });

  source = source.replace(/\$\$([^$\n]+)\$\$/g, (_, math) => {
    const token = `\u0000INLINE${inlineParts.length}\u0000`;
    inlineParts.push(renderMathInline(math));
    return token;
  });

  source = source.replace(/\$([^$\n]+)\$/g, (_, math) => {
    if (math.trim() !== math) return `$${math}$`;
    const token = `\u0000INLINE${inlineParts.length}\u0000`;
    inlineParts.push(renderMathInline(math));
    return token;
  });

  let html = markdownEscapeHtml(source);
  html = html.replace(/!\[([^\]]*)\]\(([^)\s]+)\)/g, (_, label, url) => {
    const safeUrl = sanitizeMarkdownUrl(url);
    if (!safeUrl) return label;
    return `<span class="markdown-image-wrap"><img src="${markdownEscapeHtml(safeUrl)}" alt="${markdownEscapeHtml(label)}"></span>`;
  });
  html = html.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (_, label, url) => {
    const safeUrl = sanitizeMarkdownUrl(url);
    if (!safeUrl) return label;
    return `<a href="${markdownEscapeHtml(safeUrl)}" target="_blank" rel="noopener noreferrer">${label}</a>`;
  });
  html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/__([^_]+)__/g, "<strong>$1</strong>");
  html = html.replace(/\*([^*\n]+)\*/g, "<em>$1</em>");
  html = html.replace(/_([^_\n]+)_/g, "<em>$1</em>");
  html = unescapeMarkdownPunctuation(html);
  for (const [index, part] of inlineParts.entries()) {
    html = html.replaceAll(`\u0000INLINE${index}\u0000`, part);
  }
  return html;
}

function closeMarkdownList(state, output) {
  if (!state.listType) return;
  output.push(`</${state.listType}>`);
  state.listType = "";
}

function openMarkdownList(type, state, output) {
  if (state.listType === type) return;
  closeMarkdownList(state, output);
  state.listType = type;
  output.push(`<${type}>`);
}

function flushMarkdownParagraph(paragraph, state, output) {
  if (!paragraph.length) return;
  closeMarkdownList(state, output);
  output.push(`<p>${renderInlineMarkdown(paragraph.join(" "))}</p>`);
  paragraph.length = 0;
}

function parseMarkdownTableRow(line) {
  return line
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((cell) => cell.trim());
}

function isMarkdownTableSeparator(line) {
  const cells = parseMarkdownTableRow(line);
  return cells.length > 1 && cells.every((cell) => /^:?-{3,}:?$/.test(cell));
}

function isMarkdownTableStart(line, nextLine) {
  return line.includes("|") && nextLine && isMarkdownTableSeparator(nextLine);
}

function renderMarkdownTable(headerLine, separatorLine, bodyLines) {
  const headers = parseMarkdownTableRow(headerLine);
  const alignments = parseMarkdownTableRow(separatorLine).map((cell) => {
    if (cell.startsWith(":") && cell.endsWith(":")) return "center";
    if (cell.endsWith(":")) return "right";
    return "left";
  });
  const rows = bodyLines.map(parseMarkdownTableRow);
  const th = headers
    .map((cell, index) => `<th style="text-align:${alignments[index] || "left"}">${renderInlineMarkdown(cell)}</th>`)
    .join("");
  const tr = rows
    .map((row) => {
      const td = headers
        .map((_, index) => {
          const cell = row[index] || "";
          return `<td style="text-align:${alignments[index] || "left"}">${renderInlineMarkdown(cell)}</td>`;
        })
        .join("");
      return `<tr>${td}</tr>`;
    })
    .join("");
  return `<div class="markdown-table-wrap"><table><thead><tr>${th}</tr></thead><tbody>${tr}</tbody></table></div>`;
}

function renderMarkdown(text) {
  const lines = String(text ?? "").replace(/\r\n/g, "\n").split("\n");
  const output = [];
  const paragraph = [];
  const state = { listType: "", inCode: false, codeLines: [], codeLang: "" };

  for (let index = 0; index < lines.length; index += 1) {
    const rawLine = lines[index];
    const line = rawLine.replace(/\s+$/, "");
    const fence = line.match(/^```([\w-]*)\s*$/);
    if (fence) {
      if (state.inCode) {
        output.push(`<pre><code>${markdownEscapeHtml(state.codeLines.join("\n"))}</code></pre>`);
        state.inCode = false;
        state.codeLines = [];
        state.codeLang = "";
      } else {
        flushMarkdownParagraph(paragraph, state, output);
        state.inCode = true;
        state.codeLang = fence[1] || "";
      }
      continue;
    }

    if (state.inCode) {
      state.codeLines.push(rawLine);
      continue;
    }

    if (!line.trim()) {
      flushMarkdownParagraph(paragraph, state, output);
      closeMarkdownList(state, output);
      continue;
    }

    const trimmedLine = line.trim();
    if (trimmedLine.startsWith("\\[")) {
      const block = collectDelimitedMath(lines, index, "\\[", "\\]");
      if (block) {
        flushMarkdownParagraph(paragraph, state, output);
        closeMarkdownList(state, output);
        output.push(renderMathBlock(block.content));
        index = block.endIndex;
        continue;
      }
    }

    if (trimmedLine.startsWith("$$")) {
      const block = collectDelimitedMath(lines, index, "$$", "$$");
      if (block) {
        flushMarkdownParagraph(paragraph, state, output);
        closeMarkdownList(state, output);
        output.push(renderMathBlock(block.content));
        index = block.endIndex;
        continue;
      }
    }

    if (/^\\begin\{/.test(trimmedLine)) {
      const block = collectMathEnvironment(lines, index);
      if (block) {
        flushMarkdownParagraph(paragraph, state, output);
        closeMarkdownList(state, output);
        output.push(renderMathBlock(block.content));
        index = block.endIndex;
        continue;
      }
    }

    const nextLine = lines[index + 1]?.replace(/\s+$/, "");
    if (isMarkdownTableStart(line, nextLine)) {
      flushMarkdownParagraph(paragraph, state, output);
      closeMarkdownList(state, output);
      const bodyLines = [];
      index += 2;
      while (index < lines.length && lines[index].includes("|") && lines[index].trim()) {
        bodyLines.push(lines[index].replace(/\s+$/, ""));
        index += 1;
      }
      index -= 1;
      output.push(renderMarkdownTable(line, nextLine, bodyLines));
      continue;
    }

    const heading = line.match(/^(#{1,4})\s+(.+)$/);
    if (heading) {
      flushMarkdownParagraph(paragraph, state, output);
      const level = heading[1].length + 1;
      output.push(`<h${level}>${renderInlineMarkdown(heading[2])}</h${level}>`);
      continue;
    }

    const quote = line.match(/^>\s?(.+)$/);
    if (quote) {
      flushMarkdownParagraph(paragraph, state, output);
      output.push(`<blockquote>${renderInlineMarkdown(quote[1])}</blockquote>`);
      continue;
    }

    const ordered = line.match(/^\s*\d+\.\s+(.+)$/);
    if (ordered) {
      flushMarkdownParagraph(paragraph, state, output);
      openMarkdownList("ol", state, output);
      output.push(`<li>${renderInlineMarkdown(ordered[1])}</li>`);
      continue;
    }

    const unordered = line.match(/^\s*[-*]\s+(.+)$/);
    if (unordered) {
      flushMarkdownParagraph(paragraph, state, output);
      openMarkdownList("ul", state, output);
      output.push(`<li>${renderInlineMarkdown(unordered[1])}</li>`);
      continue;
    }

    paragraph.push(line.trim());
  }

  if (state.inCode) {
    output.push(`<pre><code>${markdownEscapeHtml(state.codeLines.join("\n"))}</code></pre>`);
  }
  flushMarkdownParagraph(paragraph, state, output);
  closeMarkdownList(state, output);
  return output.join("");
}

window.renderMarkdown = renderMarkdown;
