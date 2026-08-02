import { useEffect, useRef } from "react";
import {
  ArrowLeft,
  ChevronLeft,
  ChevronRight,
  Clock3,
  ExternalLink,
  FileText,
  Fingerprint,
  Globe2,
  UserRound,
} from "lucide-react";

import type { ItemRecord } from "../types";

interface ItemDetailPanelProps {
  item: ItemRecord;
  index: number;
  total: number;
  onBack: () => void;
  onPrevious?: () => void;
  onNext?: () => void;
}

function metadataText(item: ItemRecord, keys: string[]): string {
  for (const key of keys) {
    const value = item.metadata[key];
    if (value !== null && value !== undefined && value !== "") {
      return typeof value === "string" ? value : JSON.stringify(value);
    }
  }
  return "";
}

function fullDate(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(parsed);
}

export function ItemDetailPanel({ item, index, total, onBack, onPrevious, onNext }: ItemDetailPanelProps) {
  const headingRef = useRef<HTMLHeadingElement>(null);
  let hostname = item.url;
  try {
    hostname = new URL(item.url).hostname;
  } catch {
    // Preserve the source value for malformed legacy records.
  }
  const source = metadataText(item, ["source", "siteName", "site_name"]) || hostname;
  const author = metadataText(item, ["author", "byline", "authors"]) || "未提供";
  const publishedAt = metadataText(item, ["publishedAt", "published_at", "publishedTime", "published_time"]) || "未提供";
  const paragraphs = item.content
    .split(/\r?\n{2,}/)
    .map((paragraph) => paragraph.trim())
    .filter(Boolean);

  useEffect(() => {
    headingRef.current?.focus();
  }, [item.id]);

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      const target = event.target instanceof HTMLElement ? event.target : null;
      if (target?.closest("input, textarea, select, [contenteditable='true']")) return;
      if (event.altKey || event.ctrlKey || event.metaKey) return;
      if (event.key === "Escape") onBack();
      if (event.key === "ArrowLeft" && onPrevious) onPrevious();
      if (event.key === "ArrowRight" && onNext) onNext();
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onBack, onNext, onPrevious]);

  return (
    <section className="item-detail-view" aria-labelledby="item-detail-title">
      <header className="item-detail-toolbar">
        <button className="button" type="button" onClick={onBack}>
          <ArrowLeft size={15} />返回结果
        </button>
        <span className="item-detail-position">第 {index + 1} 条 / 共 {total} 条</span>
        <div className="item-detail-actions">
          <button className="icon-button" type="button" onClick={onPrevious} disabled={!onPrevious} title="上一条" aria-label="上一条">
            <ChevronLeft size={16} />
          </button>
          <button className="icon-button" type="button" onClick={onNext} disabled={!onNext} title="下一条" aria-label="下一条">
            <ChevronRight size={16} />
          </button>
          <a className="button" href={item.url} target="_blank" rel="noreferrer">
            <ExternalLink size={14} />打开原文
          </a>
        </div>
      </header>

      <div className="item-detail-layout">
        <article className="item-detail-document">
          <div className="item-detail-kicker"><Globe2 size={14} /><span>{source}</span><code>{hostname}</code></div>
          <h1 ref={headingRef} id="item-detail-title" tabIndex={-1}>{item.title}</h1>
          <div className="item-detail-byline">
            <span><UserRound size={13} />{author}</span>
            <span><Clock3 size={13} />{publishedAt}</span>
          </div>
          <div className="item-detail-body">
            {paragraphs.length ? paragraphs.map((paragraph, paragraphIndex) => (
              <p key={`${item.id}-${paragraphIndex}`}>{paragraph}</p>
            )) : <p className="item-detail-empty">本条结果没有正文内容。</p>}
          </div>
        </article>

        <aside className="item-detail-facts" aria-label="采集信息">
          <header><FileText size={15} /><strong>采集信息</strong></header>
          <dl>
            <div><dt>来源</dt><dd>{source}</dd></div>
            <div><dt>作者</dt><dd>{author}</dd></div>
            <div><dt>原始发布时间</dt><dd>{publishedAt}</dd></div>
            <div><dt>采集时间</dt><dd>{fullDate(item.created_at)}</dd></div>
            <div><dt>内容类型</dt><dd>{item.media_type}</dd></div>
            <div><dt>正文长度</dt><dd>{item.content.length.toLocaleString("zh-CN")} 字符</dd></div>
          </dl>
          <div className="item-detail-id"><Fingerprint size={14} /><span><small>外部 ID</small><code>{item.external_id}</code></span></div>
          <details>
            <summary>完整元数据</summary>
            <pre>{JSON.stringify(item.metadata, null, 2)}</pre>
          </details>
        </aside>
      </div>
    </section>
  );
}
