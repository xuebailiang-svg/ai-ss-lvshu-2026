import type {ReactNode} from 'react';
import {Typography} from 'antd';

type MarkdownReportProps = {
  content: string;
  showToc?: boolean;
};

type HeadingItem = {
  id: string;
  level: number;
  text: string;
};

function headingId(text: string, index: number) {
  const normalized = text
    .replace(/\*\*/g, '')
    .replace(/[^\p{L}\p{N}\u4e00-\u9fff]+/gu, '-')
    .replace(/^-+|-+$/g, '')
    .toLowerCase();
  return `report-${normalized || 'section'}-${index}`;
}

function inlineContent(text: string): ReactNode[] {
  const pattern = /(\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)|\*\*([^*]+)\*\*|`([^`]+)`|\*([^*]+)\*)/g;
  const result: ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  let key = 0;

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      result.push(<span key={key++}>{text.slice(lastIndex, match.index)}</span>);
    }
    if (match[2] && match[3]) {
      result.push(
        <a key={key++} href={match[3]} target="_blank" rel="noreferrer">
          {match[2]}
        </a>,
      );
    } else if (match[4]) {
      result.push(<strong key={key++}>{match[4]}</strong>);
    } else if (match[5]) {
      result.push(<code key={key++}>{match[5]}</code>);
    } else if (match[6]) {
      result.push(<em key={key++}>{match[6]}</em>);
    }
    lastIndex = pattern.lastIndex;
  }

  if (lastIndex < text.length) {
    result.push(<span key={key}>{text.slice(lastIndex)}</span>);
  }
  return result;
}

function splitTableRow(line: string) {
  return line
    .trim()
    .replace(/^\|/, '')
    .replace(/\|$/, '')
    .split('|')
    .map(cell => cell.trim());
}

function isTableSeparator(line: string) {
  const cells = splitTableRow(line);
  return cells.length > 0 && cells.every(cell => /^:?-{3,}:?$/.test(cell));
}

function normalizeMarkdown(content: string) {
  return content
    .replace(/\r\n/g, '\n')
    // 部分模型会把 Markdown 表格压缩成一行，用 “| |” 表示相邻行。
    // 先恢复换行，避免报告把表格当作普通段落直接显示。
    .replace(/\|\s+\|/g, '|\n|');
}

export default function MarkdownReport({content, showToc = false}: MarkdownReportProps) {
  const lines = normalizeMarkdown(content).split('\n');
  const blocks: ReactNode[] = [];
  const headings: HeadingItem[] = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index].trim();
    if (!line) {
      index += 1;
      continue;
    }

    const heading = line.match(/^(#{1,6})\s+(.+)$/);
    if (heading) {
      const level = Math.min(5, heading[1].length) as 1 | 2 | 3 | 4 | 5;
      const id = headingId(heading[2], index);
      headings.push({id, level: heading[1].length, text: heading[2].replace(/\*\*/g, '')});
      blocks.push(
        <Typography.Title id={id} key={`heading-${index}`} level={level}>
          {inlineContent(heading[2])}
        </Typography.Title>,
      );
      index += 1;
      continue;
    }

    if (
      line.includes('|')
      && index + 1 < lines.length
      && isTableSeparator(lines[index + 1])
    ) {
      const headers = splitTableRow(line);
      const rows: string[][] = [];
      index += 2;
      while (index < lines.length && lines[index].trim() && lines[index].includes('|')) {
        rows.push(splitTableRow(lines[index]));
        index += 1;
      }
      blocks.push(
        <div className="markdown-table-wrap" key={`table-${index}`}>
          <table>
            <thead>
              <tr>{headers.map((cell, cellIndex) => <th key={cellIndex}>{inlineContent(cell)}</th>)}</tr>
            </thead>
            <tbody>
              {rows.map((row, rowIndex) => (
                <tr key={rowIndex}>
                  {headers.map((_, cellIndex) => (
                    <td key={cellIndex}>{inlineContent(row[cellIndex] || '')}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      );
      continue;
    }

    if (/^>\s?/.test(line)) {
      const quote: string[] = [];
      while (index < lines.length && /^>\s?/.test(lines[index].trim())) {
        quote.push(lines[index].trim().replace(/^>\s?/, ''));
        index += 1;
      }
      blocks.push(<blockquote key={`quote-${index}`}>{inlineContent(quote.join(' '))}</blockquote>);
      continue;
    }

    if (/^([-*_])(?:\s*\1){2,}$/.test(line)) {
      blocks.push(<hr key={`rule-${index}`} />);
      index += 1;
      continue;
    }

    if (/^[-*]\s+/.test(line)) {
      const items: string[] = [];
      while (index < lines.length && /^[-*]\s+/.test(lines[index].trim())) {
        items.push(lines[index].trim().replace(/^[-*]\s+/, ''));
        index += 1;
      }
      blocks.push(
        <ul key={`list-${index}`}>
          {items.map((item, itemIndex) => <li key={itemIndex}>{inlineContent(item)}</li>)}
        </ul>,
      );
      continue;
    }

    if (/^\d+[.)]\s+/.test(line)) {
      const items: string[] = [];
      while (index < lines.length && /^\d+[.)]\s+/.test(lines[index].trim())) {
        items.push(lines[index].trim().replace(/^\d+[.)]\s+/, ''));
        index += 1;
      }
      blocks.push(
        <ol key={`ordered-list-${index}`}>
          {items.map((item, itemIndex) => <li key={itemIndex}>{inlineContent(item)}</li>)}
        </ol>,
      );
      continue;
    }

    const paragraph: string[] = [line];
    index += 1;
    while (
      index < lines.length
      && lines[index].trim()
      && !/^(#{1,6})\s+/.test(lines[index].trim())
      && !/^[-*]\s+/.test(lines[index].trim())
      && !/^\d+[.)]\s+/.test(lines[index].trim())
      && !/^>\s?/.test(lines[index].trim())
      && !/^([-*_])(?:\s*\1){2,}$/.test(lines[index].trim())
      && !(
        lines[index].includes('|')
        && index + 1 < lines.length
        && isTableSeparator(lines[index + 1])
      )
    ) {
      paragraph.push(lines[index].trim());
      index += 1;
    }
    blocks.push(
      <Typography.Paragraph key={`paragraph-${index}`}>
        {inlineContent(paragraph.join(' '))}
      </Typography.Paragraph>,
    );
  }

  const tocItems = headings.filter(item => item.level === 2 || item.level === 3);

  return (
    <article className="markdown-report">
      {showToc && tocItems.length > 2 && (
        <nav className="markdown-report-toc" aria-label="报告目录">
          <Typography.Text strong>报告目录</Typography.Text>
          <ol>
            {tocItems.map(item => (
              <li key={item.id} className={item.level === 3 ? 'subsection' : undefined}>
                <a href={`#${item.id}`}>{item.text}</a>
              </li>
            ))}
          </ol>
        </nav>
      )}
      {blocks}
    </article>
  );
}
