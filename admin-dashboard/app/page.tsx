"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

type Tab = "Dashboard" | "Conversations" | "Escalations" | "Analytics";
type ConversationStatus = "AI Resolved" | "Escalated" | "Human Resolved";
type Customer = { id: number; name: string; email: string };
type ConversationOrder = { id: number; external_order_id: string; product_name: string; status: string };
type ConversationSummary = {
  conversation_id: number;
  customer: Customer;
  order: ConversationOrder | null;
  status: string;
  created_at: string;
  updated_at: string;
};
type ConversationMessage = {
  id: number;
  sender_type: string;
  content: string;
  intent: string | null;
  confidence: number | null;
  created_at: string;
};
type ConversationDetail = ConversationSummary & { messages: ConversationMessage[] };
type AdminOrder = {
  id: number;
  external_order_id: string;
  customer: Customer;
  product_name: string;
  amount: string;
  status: string;
  created_at: string;
};
type Escalation = {
  id: number;
  conversation: { id: number; status: string };
  reason: string;
  status: "OPEN" | "IN_PROGRESS" | "RESOLVED";
  assigned_agent: string | null;
  human_response: string | null;
  created_at: string;
  resolved_at: string | null;
};
type Analytics = {
  total_conversations: number;
  ai_resolved: number;
  human_escalated: number;
  open_escalations: number;
  resolution_rate: number;
};

const emptyAnalytics: Analytics = {
  total_conversations: 0,
  ai_resolved: 0,
  human_escalated: 0,
  open_escalations: 0,
  resolution_rate: 0,
};

async function supportApi<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/support/${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  const payload = await response.json().catch(() => ({})) as { detail?: string };
  if (!response.ok) throw new Error(payload.detail || "The support backend could not complete the request.");
  return payload as T;
}

function mapStatus(status: string): ConversationStatus {
  if (status === "RESOLVED") return "Human Resolved";
  if (status === "ESCALATED") return "Escalated";
  return "AI Resolved";
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat("en-IN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function formatAge(value: string) {
  const minutes = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 60_000));
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  return hours < 24 ? `${hours} hr` : `${Math.floor(hours / 24)} day`;
}

function latestAiMessage(detail?: ConversationDetail) {
  return [...(detail?.messages ?? [])].reverse().find((message) => message.sender_type === "AI");
}

function latestCustomerMessage(detail?: ConversationDetail) {
  return [...(detail?.messages ?? [])].reverse().find((message) => message.sender_type === "CUSTOMER");
}

function StatusBadge({ status }: { status: ConversationStatus }) {
  return <span className={`status status-${status.toLowerCase().replaceAll(" ", "-")}`}>{status}</span>;
}

export default function Home() {
  const [activeTab, setActiveTab] = useState<Tab>("Dashboard");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<"All" | ConversationStatus>("All");
  const [orders, setOrders] = useState<AdminOrder[]>([]);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [conversationDetails, setConversationDetails] = useState<Record<number, ConversationDetail>>({});
  const [escalations, setEscalations] = useState<Escalation[]>([]);
  const [analytics, setAnalytics] = useState<Analytics>(emptyAnalytics);
  const [selectedConversation, setSelectedConversation] = useState<number | null>(null);
  const [selectedEscalation, setSelectedEscalation] = useState<number | null>(null);
  const [draft, setDraft] = useState("");
  const [activityMessage, setActivityMessage] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const refreshData = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [savedOrders, summaries, escalationList, analyticsResult] = await Promise.all([
        supportApi<AdminOrder[]>("admin/orders"),
        supportApi<ConversationSummary[]>("admin/conversations"),
        supportApi<Escalation[]>("admin/escalations"),
        supportApi<Analytics>("admin/analytics"),
      ]);
      const [detailPairs, escalationDetails] = await Promise.all([
        Promise.all(summaries.map(async (item) => [
          item.conversation_id,
          await supportApi<ConversationDetail>(`admin/conversations/${item.conversation_id}`),
        ] as const)),
        Promise.all(escalationList.map((item) => supportApi<Escalation>(`admin/escalations/${item.id}`))),
      ]);
      setOrders(savedOrders);
      setConversations(summaries);
      setConversationDetails(Object.fromEntries(detailPairs));
      setEscalations(escalationDetails);
      setAnalytics(analyticsResult);
      setSelectedConversation((current) => summaries.some((item) => item.conversation_id === current) ? current : summaries[0]?.conversation_id ?? null);
      setSelectedEscalation((current) => escalationDetails.some((item) => item.id === current) ? current : escalationDetails[0]?.id ?? null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Dashboard data is unavailable.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void refreshData(); }, [refreshData]);

  const conversationRows = useMemo(() => conversations.map((summary) => {
    const detail = conversationDetails[summary.conversation_id];
    const aiMessage = latestAiMessage(detail);
    return {
      summary,
      detail,
      name: summary.customer.name,
      issue: latestCustomerMessage(detail)?.content ?? summary.order?.product_name ?? "Support conversation",
      status: mapStatus(summary.status),
      time: formatTime(summary.updated_at),
      order: summary.order ? `#${summary.order.external_order_id}` : "No order",
      intent: aiMessage?.intent?.replaceAll("_", " ") ?? "—",
      confidence: aiMessage?.confidence == null ? null : Math.round(aiMessage.confidence * 100),
    };
  }), [conversations, conversationDetails]);

  const filteredConversations = useMemo(() => {
    const query = search.trim().toLowerCase();
    return conversationRows.filter((item) => {
      const matchesSearch = !query || [item.name, item.issue, String(item.summary.conversation_id), item.order].some((value) => value.toLowerCase().includes(query));
      return matchesSearch && (statusFilter === "All" || item.status === statusFilter);
    });
  }, [conversationRows, search, statusFilter]);

  const selected = conversationRows.find((item) => item.summary.conversation_id === selectedConversation) ?? conversationRows[0];
  const escalation = escalations.find((item) => item.id === selectedEscalation) ?? escalations[0];
  const escalationConversation = escalation ? conversationDetails[escalation.conversation.id] : undefined;
  const escalationState = escalation?.status === "IN_PROGRESS" ? "In progress" : escalation?.status === "RESOLVED" ? "Resolved" : "Waiting";

  const metrics = [
    { label: "Total Conversations", value: String(analytics.total_conversations), code: "TC", tone: "mint", note: `${orders.length} saved orders` },
    { label: "AI Resolved", value: String(analytics.ai_resolved), code: "AI", tone: "teal", note: `${analytics.resolution_rate}% of total` },
    { label: "Escalated", value: String(analytics.human_escalated), code: "ES", tone: "amber", note: `${analytics.open_escalations} open` },
    { label: "AI Resolution Rate", value: `${analytics.resolution_rate}%`, code: "%", tone: "blue", note: "Live tenant analytics" },
  ];

  const intentStats = useMemo(() => {
    const counts = new Map<string, number>();
    for (const detail of Object.values(conversationDetails)) {
      const intent = latestAiMessage(detail)?.intent;
      if (intent) counts.set(intent, (counts.get(intent) ?? 0) + 1);
    }
    const total = [...counts.values()].reduce((sum, value) => sum + value, 0);
    return [...counts.entries()].sort((a, b) => b[1] - a[1]).map(([name, count]) => ({
      name: name.replaceAll("_", " "),
      value: total ? Math.round((count / total) * 100) : 0,
    }));
  }, [conversationDetails]);

  function navigate(tab: Tab) { setActiveTab(tab); setActivityMessage(""); }

  async function updateEscalation(payload: Record<string, string | null>, successMessage: string) {
    if (!escalation || saving) return;
    setSaving(true);
    setError("");
    try {
      await supportApi<Escalation>(`admin/escalations/${escalation.id}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      });
      setActivityMessage(successMessage);
      setDraft("");
      await refreshData();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The escalation could not be updated.");
    } finally {
      setSaving(false);
    }
  }

  function sendReply(event: FormEvent) {
    event.preventDefault();
    if (!draft.trim() || !escalation) return;
    void updateEscalation({ human_response: draft.trim() }, `Reply saved for escalation #${escalation.id}.`);
  }

  return (
    <div className="console-shell">
      <aside className="sidebar">
        <div><div className="brand-mark" aria-hidden="true">S</div><div className="brand-copy"><strong>SupportAI</strong><span>Business Console</span></div></div>
        <nav aria-label="Main navigation">{(["Dashboard", "Conversations", "Escalations", "Analytics"] as Tab[]).map((tab) => <button key={tab} className={activeTab === tab ? "nav-item active" : "nav-item"} onClick={() => navigate(tab)} aria-current={activeTab === tab ? "page" : undefined}><span className="nav-dot" aria-hidden="true" />{tab}{tab === "Escalations" && <span className="nav-count">{analytics.open_escalations}</span>}</button>)}</nav>
        <div className="sidebar-foot"><span className="connection-dot" /><div><strong>ShopX workspace</strong><small>{error ? "Backend unavailable" : "Live backend connected"}</small></div></div>
      </aside>

      <main className="main-content">
        <header className="topbar"><div><p className="eyebrow">SUPPORT OPERATIONS</p><h1>{activeTab === "Dashboard" ? "Support Dashboard" : activeTab}</h1><p className="subtitle">{activeTab === "Dashboard" && "Monitor AI conversations and customer escalations."}{activeTab === "Conversations" && "Review every customer interaction handled by your support AI."}{activeTab === "Escalations" && "Take over sensitive or low-confidence conversations."}{activeTab === "Analytics" && "Understand how your AI support operation is performing."}</p></div><div className="demo-pill"><span /> PostgreSQL live data</div></header>

        {loading && <div className="activity-message" role="status">Loading live support data…</div>}
        {error && <div className="dashboard-error" role="alert">{error}<button className="secondary-button" onClick={() => void refreshData()}>Retry</button></div>}

        {activeTab === "Dashboard" && <section className="page-section" aria-label="Dashboard overview"><div className="metric-grid">{metrics.map((metric) => <article className="metric-card" key={metric.label}><div className={`metric-icon ${metric.tone}`}>{metric.code}</div><div><span className="metric-label">{metric.label}</span><strong>{metric.value}</strong><small>{metric.note}</small></div></article>)}</div><section className="panel recent-panel"><div className="panel-head"><div><h2>Recent Conversations</h2><p>Latest PostgreSQL-backed customer activity</p></div><button className="secondary-button" onClick={() => navigate("Conversations")}>View all</button></div><div className="table-wrap"><table><thead><tr><th>Customer</th><th>Issue</th><th>Status</th><th>Updated</th></tr></thead><tbody>{conversationRows.slice(0, 4).map((item) => <tr key={item.summary.conversation_id} onClick={() => { setSelectedConversation(item.summary.conversation_id); navigate("Conversations"); }} tabIndex={0} onKeyDown={(event) => { if (event.key === "Enter") { setSelectedConversation(item.summary.conversation_id); navigate("Conversations"); } }}><td><div className="customer-cell"><span className="avatar">{item.name[0]}</span><div><strong>{item.name}</strong><small>CON-{item.summary.conversation_id}</small></div></div></td><td>{item.issue}</td><td><StatusBadge status={item.status} /></td><td>{item.time}</td></tr>)}</tbody></table>{!loading && !conversationRows.length && <div className="empty-state">No conversations have been created yet.</div>}</div></section></section>}

        {activeTab === "Conversations" && <section className="page-section conversations-layout"><div className="panel conversation-list"><div className="filter-row"><label className="search-field"><span>Search</span><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Customer, order or issue" /></label><label className="filter-field"><span>Status</span><select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as "All" | ConversationStatus)}><option>All</option><option>AI Resolved</option><option>Escalated</option><option>Human Resolved</option></select></label></div><div className="result-count">{filteredConversations.length} conversations</div><div className="conversation-items">{filteredConversations.map((item) => <button key={item.summary.conversation_id} className={selected?.summary.conversation_id === item.summary.conversation_id ? "conversation-item selected" : "conversation-item"} onClick={() => setSelectedConversation(item.summary.conversation_id)}><span className="avatar">{item.name[0]}</span><span className="conversation-summary"><strong>{item.name}<small>{item.time}</small></strong><span>{item.issue}</span><em>CON-{item.summary.conversation_id} · ShopX API</em></span><StatusBadge status={item.status} /></button>)}{!filteredConversations.length && <div className="empty-state">No conversations match your filters.</div>}</div></div>{selected ? <aside className="panel detail-panel" aria-label="Selected conversation"><div className="detail-head"><div><p>CON-{selected.summary.conversation_id}</p><h2>{selected.name}</h2></div><StatusBadge status={selected.status} /></div><div className="context-grid"><div><span>Order</span><strong>{selected.order}</strong></div><div><span>Intent</span><strong>{selected.intent}</strong></div><div><span>AI confidence</span><strong>{selected.confidence == null ? "—" : `${selected.confidence}%`}</strong></div><div><span>Updated</span><strong>{selected.time}</strong></div></div><div className="chat-thread">{selected.detail?.messages.map((message) => <div key={message.id} className={`chat-message ${message.sender_type.toLowerCase()}`}><span>{message.sender_type === "CUSTOMER" ? selected.name : message.sender_type === "AI" ? "SupportAI" : "Human agent"} · {formatTime(message.created_at)}</span><p>{message.content}</p></div>)}</div>{selected.status === "Escalated" && <button className="primary-button full" onClick={() => { const match = escalations.find((item) => item.conversation.id === selected.summary.conversation_id); if (match) setSelectedEscalation(match.id); navigate("Escalations"); }}>Open escalation</button>}</aside> : <aside className="panel detail-panel empty-state">Select a conversation when one becomes available.</aside>}</section>}

        {activeTab === "Escalations" && <section className="page-section escalation-layout"><div className="panel escalation-queue"><div className="panel-head"><div><h2>Escalation Queue</h2><p>{analytics.open_escalations} cases require human review</p></div></div><div className="queue-items">{escalations.map((item) => { const detail = conversationDetails[item.conversation.id]; const customerMessage = latestCustomerMessage(detail); return <button key={item.id} className={escalation?.id === item.id ? "queue-card selected" : "queue-card"} onClick={() => { setSelectedEscalation(item.id); setActivityMessage(""); }}><div className="queue-top"><strong>{detail?.customer.name ?? `Conversation ${item.conversation.id}`}</strong><span className="priority priority-medium">{item.status.replaceAll("_", " ")}</span></div><h3>{customerMessage?.content ?? "Support escalation"}</h3><p>{item.reason}</p><div className="queue-meta"><span>ESC-{item.id}</span><span>CON-{item.conversation.id}</span><span>{formatAge(item.created_at)} old</span></div></button>; })}{!escalations.length && <div className="empty-state">No escalations have been created.</div>}</div></div>{escalation && escalationConversation ? <div className="panel takeover-panel"><div className="detail-head"><div><p>ESC-{escalation.id} · {escalationConversation.order ? `#${escalationConversation.order.external_order_id}` : "No order"}</p><h2>{escalationConversation.customer.name}: {latestCustomerMessage(escalationConversation)?.content ?? "Support escalation"}</h2></div><span className={`case-state state-${escalationState.toLowerCase().replace(" ", "-")}`}>{escalationState}</span></div><div className="escalation-reason"><span>Why AI escalated</span><p>{escalation.reason}{escalation.assigned_agent ? ` Assigned to ${escalation.assigned_agent}.` : ""}</p></div><div className="chat-thread compact">{escalationConversation.messages.map((message) => <div key={message.id} className={`chat-message ${message.sender_type.toLowerCase()}`}><span>{message.sender_type === "CUSTOMER" ? escalationConversation.customer.name : "SupportAI"} · {formatTime(message.created_at)}</span><p>{message.content}</p></div>)}{escalation.human_response && <div className="chat-message agent"><span>{escalation.assigned_agent ?? "Human agent"}</span><p>{escalation.human_response}</p></div>}</div>{escalationState === "Waiting" ? <button className="primary-button full" disabled={saving} onClick={() => void updateEscalation({ assigned_agent: "ShopX Support Agent", status: "IN_PROGRESS" }, `Escalation #${escalation.id} is now in progress.`)}>Take over case</button> : escalationState === "In progress" ? <form className="reply-box" onSubmit={sendReply}><label htmlFor="agent-reply">Human agent reply</label><textarea id="agent-reply" value={draft} onChange={(event) => setDraft(event.target.value)} placeholder={`Reply to ${escalationConversation.customer.name}…`} rows={3} /><div><button type="submit" disabled={saving || !draft.trim()} className="secondary-button">Save reply</button><button type="button" disabled={saving} className="primary-button" onClick={() => void updateEscalation({ status: "RESOLVED", human_response: draft.trim() || escalation.human_response }, `Escalation #${escalation.id} resolved.`)}>Resolve case</button></div></form> : <div className="resolved-callout">✓ Case resolved by human support{escalation.resolved_at ? ` on ${formatTime(escalation.resolved_at)}` : ""}</div>}{activityMessage && <div className="activity-message" role="status">{activityMessage}</div>}</div> : <div className="panel takeover-panel empty-state">Select an escalation when one becomes available.</div>}</section>}

        {activeTab === "Analytics" && <section className="page-section analytics-page"><div className="analytics-summary"><article><span>AI resolution</span><strong>{analytics.resolution_rate}%</strong><small>{analytics.ai_resolved} of {analytics.total_conversations} conversations</small></article><article><span>Open escalations</span><strong>{analytics.open_escalations}</strong><small>Current human support queue</small></article><article><span>Human takeover</span><strong>{analytics.total_conversations ? Math.round((analytics.human_escalated / analytics.total_conversations) * 100) : 0}%</strong><small>{analytics.human_escalated} distinct conversations</small></article></div><div className="analytics-grid"><section className="panel chart-card"><div className="panel-head"><div><h2>Conversation outcomes</h2><p>AI resolved vs human escalated</p></div></div><div className="bar-chart" aria-label="Conversation outcome chart">{[{ d: "AI resolved", a: analytics.total_conversations ? (analytics.ai_resolved / analytics.total_conversations) * 100 : 0, e: 0 }, { d: "Escalated", a: 0, e: analytics.total_conversations ? (analytics.human_escalated / analytics.total_conversations) * 100 : 0 }].map((bar) => <div className="bar-column" key={bar.d}><div className="bars"><span className="bar ai-bar" style={{ height: `${bar.a}%` }}/><span className="bar esc-bar" style={{ height: `${bar.e}%` }}/></div><small>{bar.d}</small></div>)}</div><div className="chart-legend"><span><i className="legend-ai"/> AI resolved</span><span><i className="legend-esc"/> Escalated</span></div></section><section className="panel intent-card"><div className="panel-head"><div><h2>Customer intents</h2><p>Classifications persisted with AI messages</p></div></div><div className="intent-list">{intentStats.map((intent) => <div className="intent-row" key={intent.name}><div><span>{intent.name}</span><strong>{intent.value}%</strong></div><div className="progress-track"><span style={{ width: `${intent.value}%` }}/></div></div>)}{!intentStats.length && <div className="empty-state">No classified messages yet.</div>}</div></section></div><div className="insight-card"><span>Live insight</span><strong>{intentStats[0] ? `${intentStats[0].name} is the most common stored intent.` : "Insights will appear after customer conversations."}</strong><p>These values are calculated from the current ShopX tenant’s PostgreSQL-backed conversations.</p></div></section>}
      </main>
    </div>
  );
}
